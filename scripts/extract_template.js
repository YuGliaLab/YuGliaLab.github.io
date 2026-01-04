
const fs = require('fs');
const path = require('path');

const inputPath = path.join(__dirname, '../site/index.html');
const outputPath = path.join(__dirname, '../templates/layout.njk');

let content = fs.readFileSync(inputPath, 'utf8');

// 1. Replace Title
content = content.replace(/<title>.*?<\/title>/, '<title>{{ title }}</title>');

// 2. Replace Meta Description
content = content.replace(/<meta content="[^"]*" name="description">/, '<meta content="{{ description }}" name="description">');

// 3. Replace Canonical
content = content.replace(/<link href="[^"]*" rel="canonical"\/>/, '<link href="{{ canonical_url }}" rel="canonical"/>');

// 4. Replace OG/Twitter meta
content = content.replace(/<meta content="[^"]*" property="og:title">/, '<meta content="{{ title }}" property="og:title">');
content = content.replace(/<meta content="[^"]*" property="og:description"\/>/, '<meta content="{{ description }}" property="og:description"/>');
content = content.replace(/<meta content="[^"]*" name="twitter:title"\/>/, '<meta content="{{ title }}" name="twitter:title"/>');
content = content.replace(/<meta content="[^"]*" name="twitter:description"\/>/, '<meta content="{{ description }}" name="twitter:description"/>');

// 5. Replace Assets paths
content = content.replace(/(["'])assets\//g, '$1{{ root_path }}assets/');
content = content.replace(/(["'])\.\.\/assets\//g, '$1{{ root_path }}assets/'); // Handle existing ../assets/ if any

// 5.5 Remove external srcset to fix localhost image loading
content = content.replace(/\ssrcset="[^"]*"/g, '');

// 6. Replace Page ID x2541 with {{ page_id }}
// We do this BEFORE extracting the block content so we can identify the styles.

// Replace the page specific CSS block
const styleRegex = /<style id="css_x2541">[\s\S]*?<\/style>/;
content = content.replace(styleRegex, '{% block page_css %}{% endblock %}');

// Replace compCssMappers style block
const mapperRegex = /<style id="compCssMappers_x2541">[\s\S]*?<\/style>/;
content = content.replace(mapperRegex, '{% block page_css_mappers %}{% endblock %}');

// 6.5 Add our responsive overrides stylesheet (loaded after inline styles)
// This keeps mobile/desktop responsive behavior even if the template is re-extracted.
if (!content.includes('assets/responsive.css')) {
    content = content.replace(
        /<\/head>/i,
        '\n<link href="{{ root_path }}assets/responsive.css" rel="stylesheet"/>\n</head>'
    );
}

// Replace all other x2541 occurrences
content = content.replace(/x2541/g, '{{ page_id }}');

// 7. Extract Main Content
// Structure: <div class="HT5ybB"> ... </div></div></div></div></main>
// We want to replace the content inside HT5ybB.

const startMarker = '<div class="HT5ybB">';
const endMarker = '</div></div></div></div></main>';

const startIndex = content.indexOf(startMarker);
const endIndex = content.lastIndexOf(endMarker);

if (startIndex !== -1 && endIndex !== -1) {
    const pre = content.substring(0, startIndex + startMarker.length);
    const post = content.substring(endIndex); // This includes the endMarker
    
    // We want to insert the block between pre and the closing div of HT5ybB
    // Wait, endMarker is `</div></div></div></div></main>`
    // The hierarchy is:
    // <main ...>
    //   <div id="SITE_PAGES">
    //     <div id="SITE_PAGES_TRANSITION_GROUP">
    //       <div id="{{ page_id }}">
    //         <div class="PFkO7r ..."></div>
    //         <div class="HT5ybB">
    //            CONTENT IS HERE
    //         </div>
    //       </div>
    //     </div>
    //   </div>
    // </main>
    
    // So there are 4 closing divs before </main>.
    // 1. HT5ybB
    // 2. {{ page_id }} div
    // 3. TRANSITION_GROUP
    // 4. SITE_PAGES
    
    // So `</div></div></div></div></main>` is correct.
    // We want to preserve the closing div of HT5ybB.
    // So we want to replace everything between `startMarker` and `</div>` (the first one in the sequence of 4).
    
    // Let's rely on the endMarker being unique enough.
    // The content inside HT5ybB ends right before those 4 closing divs.
    
    // So `content.substring(startIndex + startMarker.length, endIndex)` is the content we want to replace.
    
    content = pre + '\n{% block content %}{% endblock %}\n' + post;
    console.log('Successfully replaced content block.');
} else {
    console.error('Could not find content markers');
}

fs.writeFileSync(outputPath, content);
console.log('Template extracted to ' + outputPath);
