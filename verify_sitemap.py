from xml.etree import ElementTree
from blog import app
import sys
import requests
import sys
from BeautifulSoup import BeautifulStoneSoup as Soup

def analyze_site_map():
    r = requests.get('{}{}sitemap.xml'.format(app.config['WEB_PROTOCOL'], app.config['DOMAIN']))

    soup = Soup(r.content)
    locs = soup.findAll('loc')
    return [loc.string for loc in locs]

def main():
    bad = []

    for loc in analyze_site_map():
        r = requests.get(loc)
        print loc, r.url, r.status_code
        if loc != r.url or r.status_code != 200:
            bad.append((loc, r.url, r.status_code))

    if bad:
        print "Failed:\n"
        for b in bad:
            print b

        return 1

    print "Success"
    return 0

if __name__ == '__main__':
    try:
        exit = main()
    except Exception as ex:
        sys.stderr.write(str(ex))
        exit = 1

    sys.exit(exit)
