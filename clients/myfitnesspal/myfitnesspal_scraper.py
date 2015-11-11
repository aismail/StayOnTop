from collections import defaultdict, Counter
import copy
import os
import subprocess
import tempfile

import arrow
import pandas
import requests

DATE_FORMAT = 'M/D/YYYY'
MONTH_FORMAT = 'YYYY - MM - MMMM'
DAY_OF_WEEK_FORMAT = 'd - dddd'
FOOD_METRICS = ['calories', 'carbs', 'fat', 'protein', 'sugar', 'fiber', 'sodium', 'cholesterol']

def split_into_food_name_and_qty(food_log_entry):
    """Given a food log entry, split it into food name and quantities.
    The tricky part is when the food name itself contains a comma."""
    last_comma_pos = food_log_entry.rfind(',')
    return (food_log_entry[0:last_comma_pos].strip(),
            food_log_entry[last_comma_pos+2:len(food_log_entry)].strip())

"""
Wrapper to facilitate the interaction with MyFitnessPal's database.
Currently using CasperJS script located within the same folder
to perform the actual HTML scrape of the necessary data.
"""
class MyFitnessPalScraper(object):

    DATE_FORMAT = 'YYYY-MM-DD'

    def __init__(self, username, password):
        self.username = username
        self.password = password

    def scrape_logs(self,
                    analyzed_username,
                    start_date,
                    end_date):

        # Need to provide these default values at runtime, instead of
        # at definition time. Otherwise, the default values will be the ones
        # when the Python interpreter finds the function definition the first
        # time (even though it might not be called until much later).
        start_date = start_date or arrow.now()
        end_date = end_date or arrow.now()

        entries = []

        i = start_date
        j = start_date.replace(years=+1)
        if j > end_date:
            j = end_date

        while i < end_date:

            # Sanity checks, we expect 'arrow' objects
            try:
                start_date_formatted = i.format(self.DATE_FORMAT)
            except AttributeError:
                raise ValueError('start_date needs to have a format() method')
            try:
                end_date_formatted = j.format(self.DATE_FORMAT)
            except AttributeError:
                raise ValueError('end_date needs to have a format() method')


            """
            Scrape MFP data via Casper.JS script to login to MFP and target
            the analyzed username. The script is exort_myfitnesspal.js
            and is located within the same folder as this file.
            """
            script_path = os.path.dirname(os.path.realpath(__file__))
            (fd, export_file) = tempfile.mkstemp(suffix='csv')

            subprocess.call(["casperjs",
                             "%s/myfitnesspal_scraper.js" % script_path,
                             "--ssl-protocol=any",
                             "--user=%s" % self.username,
                             "--password=%s" % self.password,
                             "--file=%s" % export_file,
                             "--analyzed_username=%s" % analyzed_username,
                             "--start_date=%s" % start_date_formatted,
                             "--end_date=%s" % end_date_formatted])

            # Prefer pandas for automatic type casting of numeric values for later postprocessing
            reader = pandas.read_csv(export_file)

            os.close(fd)
            os.remove(export_file)

            entries.extend(reader.to_dict('records'))

            i = j
            j = j.replace(years=+1)
            if j > end_date:
                j = end_date

        result = FoodLog([FoodLogEntry(e) for e in entries])
        result.start_date = start_date
        result.end_date = end_date
        return result

def default_macros_daily_entry():
    result = Counter()
    result['meals'] = defaultdict(Counter)
    return result

class FoodLogEntry(dict):

    def get_name(self):
        name, qty = split_into_food_name_and_qty(self['food'])
        return name

    def get_qty(self):
        name, qty = split_into_food_name_and_qty(self['food'])
        return qty

    def get_meal(self):
        return self['meal'].lower()

    def macros(self):
        result = {}
        for k, v in self.iteritems():
            if k in FOOD_METRICS:
                result[k] = v
        return result

    def protein_to_fat_ratio(self):
        if ('protein' in self) and ('fat' in self):
            return float(self['protein']) / max(float(self['fat']), 1.0)

class FoodLog(list):

    def get_unique_meal_names(self):
        """Retrieve the names of the meals from MyFitnessPal food log data.

        We need to do this because the meal names (and their number, up to 6)
        are configurable by users.
        """

        result = set()
        for log_entry in self:
            result.add(log_entry['meal'].lower())

        return sorted(list(result))

    def daily_macros(self, tokens=None, include_zero='False'):
        """Returns a history of daily macro values extracted from the
        food log."""
        days = defaultdict(default_macros_daily_entry)

        for entry in self:
            if tokens is not None:
                found = False
                for token in tokens:
                    if token.lower() in entry.get_name().lower():
                        found = True
                if not found:
                    continue

            # Date coming from JS is in JS format so it's in milliseconds.
            # TODO: improve export_myfitnesspal.js so that date is an UTC timestamp
            day = arrow.get(entry['date'] / 1000)
            meal = entry['meal'].lower()
            for k, v in entry.iteritems():
                if k in FOOD_METRICS:
                    days[day][k] += v
                    days[day]['meals'][meal][k] += v

        result = []
        meal_names = self.get_unique_meal_names()
        for (day, _) in arrow.Arrow.span_range('day',
                                               self.start_date,
                                               self.end_date):
            day_entry = {
                'date': day.format(DATE_FORMAT),
                'start of week': day.replace(days=-day.weekday()).format(DATE_FORMAT),
                'month': day.format(MONTH_FORMAT),
                '# of meals': len(days[day]['meals'].keys())
            }
            for metric in FOOD_METRICS:
                day_entry[metric] = days[day][metric]
            for meal_name in meal_names:
                for metric in FOOD_METRICS:
                    day_entry['%s %s' % (meal_name, metric)] = days[day]['meals'][meal_name][metric]

            result.append(day_entry)

        for day in result:
            if day['calories'] == 0 and not include_zero:
                for k, v in day.iteritems():
                    if k not in ['date', 'start of week']:
                        day[k] = ''

        return result

    def unique_foods_sorted_by_frequency(self):
        meal_names = self.get_unique_meal_names()
        unique_foods = {}
        totals = Counter()

        # Compute totals for each metric (e.g. calories, fats)
        #
        # They will be used in order to see the contribution of each food
        # towards that total, both in absolute terms and in percentages.
        for entry in self:
            for metric in FOOD_METRICS:
                totals[metric] += entry[metric]

        for entry in self:
            if entry.get_name() not in unique_foods:

                transformed_entry = {}
                for m in meal_names:
                    transformed_entry['%s frequency' % m] = 0
                transformed_entry['%s frequency' % entry.get_meal()] = 1
                transformed_entry.update({
                    'name': entry.get_name(),
                    'frequency': 1,
                    'qty': entry.get_qty(),
                })
                transformed_entry.update(entry.macros())

                for metric in FOOD_METRICS:
                    transformed_entry['total %s' % metric] = entry[metric]
                    transformed_entry['total %s percent' % metric] = entry[metric] * 100.0 / max(1, totals[metric])
                    transformed_entry['total %s percent per serving' % metric] = transformed_entry['total %s percent' % metric]

                protein_to_fat = entry.protein_to_fat_ratio()
                if protein_to_fat is not None:
                    transformed_entry['protein to fat ratio'] = protein_to_fat
                unique_foods[entry.get_name()] = transformed_entry
            else:
                existing_entry = unique_foods[entry.get_name()]
                existing_entry['frequency'] += 1
                existing_entry['%s frequency' % entry.get_meal()] += 1
                for metric in FOOD_METRICS:
                    existing_entry['total %s' % metric] += entry[metric]
                    existing_entry['total %s percent' % metric] = existing_entry['total %s' % metric] * 100.0 / max(1, totals[metric])
                    existing_entry['total %s percent per serving' % metric] = existing_entry['total %s percent' % metric] / existing_entry['frequency']

        return sorted(unique_foods.values(), key = lambda x: x['frequency'], reverse=True)

    def raw_foods_list(self):

        result = []
        meal_names = self.get_unique_meal_names()

        for entry in self:
            new_entry = copy.deepcopy(entry)
            new_entry['name'] = new_entry.pop('food')
            day = arrow.get(new_entry.pop('date') / 1000)
            new_entry['date'] = day.format(DATE_FORMAT)
            new_entry['start of week'] = day.replace(days=-day.weekday()).format(DATE_FORMAT)
            new_entry['month'] = day.format(MONTH_FORMAT)
            new_entry['day of week'] = day.format(DAY_OF_WEEK_FORMAT)
            new_entry.pop('user')
            result.append(new_entry)

        return result