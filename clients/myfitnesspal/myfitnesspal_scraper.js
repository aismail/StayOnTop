/*
    casper.js script that logs in to MyFitnessPal and export all the food diary
    data for a provided period of time.

    How to call this script:
        casperjs myfitnesspal_scraper.js --ssl-protocol=any --user=<mfp_username> \
        --password=<mfp_password> --file=<export.csv> \
        [--analyzed_username=<analyzed_username>] [--start_date=<YYYY-MM-DD>] \
        [--end_date=<YYYY-MM-DD>]
    The --ssl-protocol=any option is essential, without it the script will not
    work due to possible server SSL downgrade negotiation.
    The exported data will contain the following columns:
    - user: analyzed username (owner of the diary)
    - date: of the logged food item
    - meal: name of the meal the food item was attached to
    - food: name of the food item along with quantity
    - calories: value
    - carbs: as g
    - fat: as g
    - protein: as g
    - sugar: as g
    - fiber: as g
    - cholesterol: as mg
    - sodium: as mg
*/

// Init ------------------------
var utils = require('utils');

var casper = require('casper').create({
    verbose: true,
    logLevel: "debug",
    pageSettings: {
        userAgent: "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_9_5) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/40.0.2209.0 Safari/537.36",
        loadImages: false,
        ignoreSslErrors: true
    },
    onWaitTimeout: function() {
        casper.echo('Wait TimeOut Occured', 'ERROR');
        casper.exit(0);
    },
    onStepTimeout: function() {
        casper.echo('Step TimeOut Occured', 'ERROR');
        casper.exit(0);
    }
});

// User provided
var username = casper.cli.options.user;
var password = casper.cli.options.password;
var file = casper.cli.options.file;

if (!username || !file) {
    casper.echo('Usage: casperjs export_myfitnesspal.js --ssl-protocol=any --user==<mfp_username> --password=<mfp_password> --file=<export.csv> [--analyzed_username=<analyzed_username>] [--start_date=<YYYY-MM-DD>] [--end_date=<YYYY-MM-DD>]', 'INFO');
    casper.exit(0);
}

var analyzed_username = casper.cli.options.analyzed_username || username;
var start_date = casper.cli.options.start_date 
if (!start_date) {
    var currentTime = new Date();
    var month = currentTime.getMonth() + 1;
    var day = currentTime.getDate();
    var year = currentTime.getFullYear();
    start_date = year + "-" + month + "-" + day;
}
var end_date = casper.cli.options.end_date || start_date;


casper.echo('Grabbing diary for: [user='  + analyzed_username + '], [start_date=' + start_date + '], [end_date=' + end_date + ']');

// Functions ------------------------
casper.diaryGetDates = function() {
    return this.evaluate(function grabAvailableDates() {
        var dates = __utils__.findAll('h2.main-title-2');
        var result = Array.prototype.map.call(dates, function(node) {
            var date = Date.parse(node.innerText.trim() + " 00:00:00 GMT"); 
            return date;
        });
        return result;
    });
};

casper.diaryGetHeaders = function() {
    return this.evaluate(function grabAvailableHeaders() {
        var oneHeader = __utils__.findOne('table#food.table0 thead tr');
        var header = oneHeader.querySelectorAll('td');
        header = Array.prototype.map.call(header, function(node) {
            var label = node.innerText.trim().toLowerCase();

            // Fixes MFP nutrient field name inconsistency
            if (label === 'sugars') label = 'sugar';
            if (label === 'cholest') label = 'cholesterol';
            if (label === 'foods') label = 'food';
            return label;
        });
        var extraHeader = ['user', 'date', 'meal'];
        
        return extraHeader.concat(header);
    });
};

casper.diaryGetData = function(username, dates) {
    return this.evaluate(function(username, dates) {
        var tables = document.querySelectorAll('table#food.table0');
        var result = [];
        Array.prototype.map.call(tables, function(node, index) {

            // Each line item in a table's body can be mapped to either meal name or food item
            var currentDate = dates[index];
            var tableRows = node.querySelectorAll('tbody tr');
            var currentMeal = '';

            Array.prototype.map.call(tableRows, function(tableRow) {

                // Quite ugly, the row has a class "title" when a meal is mentioned
                var isMeal = tableRow.className && /(^|\\s)title(\\s|$)/.test(tableRow.className);
                if (isMeal) {
                    currentMeal = tableRow.innerText.trim();
                    return;
                }

                // Rows with no "title" are actual food entries
                var row = [];
                row.push(username);
                row.push(currentDate);
                row.push(currentMeal);

                for (i = 0; i < 9; i++) {
                    var val = tableRow.children[i].innerText.trim();

                    if (i == 0) {
                        // Name of the food and quantity are typically non-numeric
                        row.push(val.trim());
                    } else {
                        // Rest of the fields are integer values
                        row.push(val.replace(/[^0-9\.]/gm,''));
                    }
                }

                // Save row to queue
                result.push(row);
            });
        });
        return result;
    }, analyzed_username, dates);
}




// Start crawling ------------------------
casper.start('http://www.myfitnesspal.com/', function() {
    this.echo(this.getTitle());
});

// Login if needed ------------------------
if (password) {

    casper.waitForSelector('div.header-wrap ul#navTop a.fancylink', function() {
        // Do nothing, make sure the page has fully loaded by looking whether the login link can be selected
        this.echo('Attempt to log in.');
    });

    casper.then(function() {
        this.click('div.header-wrap ul#navTop a.fancylink');
    });

    casper.then(function() {
        this.sendKeys('div#fancybox-content form#fancy_login input[name="username"]', username);
        this.sendKeys('div#fancybox-content form#fancy_login input[name="password"]', password);
        this.click('div#fancybox-content form#fancy_login input[type="submit"]');
    });

    casper.waitForSelector("#footer #footerContent", function() {
        // Do nothing, make sure the page has fully loaded by looking whether the footer is available
        this.echo('Check if login worked.');
    });

    casper.then(function() {
        this.evaluateOrDie(function() {
            return /Log Out/.test(document.body.innerText.trim());
        }, 'Login failed.');
    });
} else {
    casper.echo('Provided password was empty, skipping authentication.');
}

// Crawl ------------------------
casper.thenOpen('http://www.myfitnesspal.com/reports/printable_diary/' + analyzed_username, function() {
    this.fill('div#content form.change-range', {
        'from': start_date,
        'ds1': start_date,
        'to': end_date,
        'ds2': end_date,
        'show_food_diary': true,
        'show_food_notes': false,
        'show_exercise_diary': false,
        'show_exercise_notes': false
    }, true);
});

casper.waitForResource(/jquery-ui\.js$/, function() {
    // Do nothing, make sure the page has fully loaded by looking whether the jquery-ui library which
    // is included in the footer has been loaded.
    this.echo('jquery-ui has been loaded.');
});

// Save data ------------------------
casper.then(function() {

    var dates = this.diaryGetDates();
    var header = this.diaryGetHeaders();

    this.echo('Iterating over ' + dates.length + ' diaries.');

    if (dates) {
        data = this.diaryGetData(analyzed_username, dates);
    }

    if (data) {
        var fs = require('fs');
        var stream = fs.open(file, 'w');

        // Start CSV with header
        stream.writeLine(header);

        this.each(data, function(self, row) {
            // Escape per CSV standard
            var output = row.map(function(value) {
                if (/[,\"]/.exec(value)) {
                    return '"' + value.toString().replace(/\"/gm,'""') + '"';
                }
                return value;
            });
            stream.writeLine(output);
        });
        stream.flush();
        stream.close(); 
    }
});

// Trigger the steps ------------------------
casper.run();