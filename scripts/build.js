
const nunjucks = require('nunjucks');
const fs = require('fs');
const path = require('path');

const env = new nunjucks.Environment(new nunjucks.FileSystemLoader(path.join(__dirname, '../templates')));

const pages = [
    {
        template: 'index.njk',
        output: 'site/index.html',
        data: {
            title: 'Yu Lab | Astrocyte Research | United States',
            description: 'This is the official site of Yu Lab at University of Illinois Urbana-Champaign. It has information of our research interests, team members and publications.',
            canonical_url: 'assets/asset_fcabbbef78b030d6',
            page_id: 'x2541',
            root_path: ''
        }
    },
    {
        template: 'about-the-pi.njk',
        output: 'site/about-the-pi/index.html',
        data: {
            title: 'About PI | Yu Laboratory',
            description: 'This page introduces the Pricipal Investigator of Yu lab at University of Illinois Urbana-Champaign',
            canonical_url: '../assets/asset_09d34ba0218b25ea',
            page_id: 'dxukg',
            root_path: '../'
        }
    },
    {
        template: 'contact.njk',
        output: 'site/contact/index.html',
        data: {
            title: 'Contact | Yu Laboratory',
            description: '',
            canonical_url: '../assets/asset_c35366a88c35ac51',
            page_id: 'ryou6',
            root_path: '../'
        }
    },
    {
        template: 'meet-the-team.njk',
        output: 'site/meet-the-team/index.html',
        data: {
            title: 'Meet the Team | Yu Laboratory',
            description: '',
            canonical_url: 'https://www.yu-lab.org/meet-the-team',
            page_id: 'ckht5',
            root_path: '../'
        }
    },
    {
        template: 'news.njk',
        output: 'site/news/index.html',
        data: {
            title: 'News | Yu Laboratory',
            description: '',
            canonical_url: '../assets/asset_6f8b2b71f23c3642',
            page_id: 'uxxqa',
            root_path: '../'
        }
    },
    {
        template: 'publications.njk',
        output: 'site/publications/index.html',
        data: {
            title: 'Programs | Yu Laboratory',
            description: '',
            canonical_url: '../assets/asset_84e6a4e7b5fa6edc',
            page_id: 'hw81d',
            root_path: '../'
        }
    }
];

pages.forEach(page => {
    try {
        let res = env.render(page.template, page.data);

        // Fix images: remove srcset and ensure src points to local assets
        res = res.replace(/srcset="[^"]*"/g, '');
        
        // Replace absolute Wix/static media URLs with local asset paths if they exist
        const assetFiles = fs.readdirSync(path.join(__dirname, '../site/assets'));
        res = res.replace(/src="([^"]*)"/g, (match, src) => {
            if (src.includes('static.sitestatic.com')) {
                const filename = src.split('/').pop().split('?')[0];
                const filenameAlt = filename.replace(/~/g, '_');
                const localMatch = assetFiles.find(f => f === filename || f === filenameAlt);
                if (localMatch) {
                    return `src="${page.data.root_path}assets/${localMatch}"`;
                }
            }
            return match;
        });

        const outputPath = path.join(__dirname, '../' + page.output);
        const outputDir = path.dirname(outputPath);
        if (!fs.existsSync(outputDir)){
            fs.mkdirSync(outputDir, { recursive: true });
        }
        fs.writeFileSync(outputPath, res);
        console.log(`Built ${page.output}`);
    } catch (e) {
        console.error(`Error building ${page.output}:`, e);
    }
});
