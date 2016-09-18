from xml.etree import ElementTree
import requests
from BeautifulSoup import BeautifulStoneSoup as Soup

r = requests.get('http://localhost:5000/sitemap.xml')

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