from clients.myfitnesspal import MyFitnessPalScraper

import arrow

if __name__ == '__main__':

	scraper = MyFitnessPalScraper(
		username='aismail85',
		password='keepreadingshockofgrey'
	)

	start_date = arrow.now().replace(years=-1)
	end_date = arrow.now().replace(days=-1)
	logs = scraper.scrape_logs(
		analyzed_username='aismail85',
		start_date=start_date,
		end_date=end_date
	)
	foods_list = logs.raw_foods_list()

	import pdb; pdb.set_trace()

