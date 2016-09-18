from xml.etree import ElementTree
from blog import app
import requests
from BeautifulSoup import BeautifulStoneSoup as Soup

r = requests.get('{}{}sitemap.xml'.format(app.config['WEB_PROTOCOL'], app.config['DOMAIN']))

soup = Soup(r.content)
locs = soup.findAll('loc')
locs = [loc.string for loc in locs]

bad = []

for loc in locs:
    r = requests.get(loc)
    print loc, r.url, r.status_code
    if loc != r.url or r.status_code != 200:
        bad.append((loc, r.url, r.status_code))

if bad:
    print "Failed:\n"
    for b in bad:
        print b
else:
    print "Success"