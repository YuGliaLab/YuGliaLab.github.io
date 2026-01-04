
const fs = require('fs');
const path = require('path');

function extractPage(inputRelPath, outputRelPath, pageId) {
    const inputPath = path.join(__dirname, '../' + inputRelPath);
    const outputPath = path.join(__dirname, '../' + outputRelPath);

    if (!fs.existsSync(inputPath)) {
        console.error(`File not found: ${inputPath}`);
        return;
    }

    const content = fs.readFileSync(inputPath, 'utf8');

    // Extract Page CSS
    const cssRegex = new RegExp(`<style id="css_${pageId}">([\\s\\S]*?)<\\/style>`);
    const cssMatch = content.match(cssRegex);
    let pageCss = cssMatch ? cssMatch[1] : '';

    // Extract Mapper CSS
    const mapperRegex = new RegExp(`<style id="compCssMappers_${pageId}">([\\s\\S]*?)<\\/style>`);
    const mapperMatch = content.match(mapperRegex);
    let pageCssMappers = mapperMatch ? mapperMatch[1] : '';

    // Extract Content
    const startMarker = '<div class="HT5ybB">';
    const endMarker = '</div></div></div></div></main>';
    
    const startIndex = content.indexOf(startMarker);
    const endIndex = content.lastIndexOf(endMarker);
    
    let pageContent = '';
    if (startIndex !== -1 && endIndex !== -1) {
        pageContent = content.substring(startIndex + startMarker.length, endIndex);
    } else {
        console.error(`Content block not found in ${inputRelPath}`);
    }
    
    // Replace assets paths in content
    const depth = inputRelPath.split('/').length - 2; 
    let rootPathPrefix = '';
    if (depth > 0) {
        rootPathPrefix = '../'.repeat(depth);
    }
    
    pageContent = pageContent.replace(/(["'(])assets\//g, '$1{{ root_path }}assets/');
    pageContent = pageContent.replace(/(["'(])\.\.\/assets\//g, '$1{{ root_path }}assets/');

    // 4. Remove external srcset to fix localhost image loading
    // Wix export includes srcset pointing to static.sitestatic.com which fails on localhost.
    // By removing it, we force the browser to use the local 'src' path.
    pageContent = pageContent.replace(/\ssrcset="[^"]*"/g, '');

    // Fix Nunjucks conflict with CSS `{#`
    pageCss = pageCss.replace(/\{#/g, '{ #');
    pageCssMappers = pageCssMappers.replace(/\{#/g, '{ #');
    pageContent = pageContent.replace(/\{#/g, '{ #');

    const templateContent = `{% extends "layout.njk" %}

{% block page_css %}
<style id="css_{{ page_id }}">
${pageCss}
</style>
{% endblock %}

{% block page_css_mappers %}
<style id="compCssMappers_{{ page_id }}">
${pageCssMappers}
</style>
{% endblock %}

{% block content %}
${pageContent}
{% endblock %}
`;

    fs.writeFileSync(outputPath, templateContent);
    console.log(`Created ${outputRelPath}`);
}

extractPage('site/index.html', 'templates/index.njk', 'x2541');
extractPage('site/about-the-pi/index.html', 'templates/about-the-pi.njk', 'dxukg');
extractPage('site/contact/index.html', 'templates/contact.njk', 'ryou6');
extractPage('site/meet-the-team/index.html', 'templates/meet-the-team.njk', 'ckht5');
extractPage('site/news/index.html', 'templates/news.njk', 'uxxqa');
extractPage('site/publications/index.html', 'templates/publications.njk', 'hw81d');
