
const fs = require('fs');
const path = require('path');

const filePath = path.join(__dirname, '../templates/about-the-pi.njk');
const content = fs.readFileSync(filePath, 'utf8');

const index = content.indexOf('{#');
if (index !== -1) {
    console.log('Found {# at index:', index);
    console.log('Context:', content.substring(index - 20, index + 20));
} else {
    console.log('Did not find {#');
}
