import html2text
import pymysql
from blog.local_settings import MYSQL_DATABASE, MYSQL_HOST, MYSQL_PASSWORD, MYSQL_PORT, MYSQL_USERNAME
from blog.models import User, Post, Comment, Wordpress, CategoryPost
from blog import db, app
from blog.views.home import get_uncategorized_id
from collections import defaultdict, namedtuple
from BeautifulSoup import BeautifulSoup
import os
import requests
from datetime import datetime
import uuid
import base64
import argparse

parser = argparse.ArgumentParser()
parser.add_argument('--no-image-download', action='store_true', dest='no_image_download', default=False)
args = parser.parse_args()
user = db.session.query(User).one()

WpPost = namedtuple('WpPost', ('id', 'title', 'content', 'creation_date', 'last_modified_date', 'post_name', 'guid'))
WpComment = namedtuple('WpComment', ('post_id', 'name', 'email', 'creation_date', 'content'))
WpMeta = namedtuple('WpMeta', ('post_id', 'meta_value'))

post_sql = 'select p.id, p.post_title, p.post_content, p.post_date, p.post_modified, p.post_name, p.guid ' \
      "FROM wp_posts p WHERE 1=1 AND p.post_status = 'publish'"

comment_sql = 'select c.comment_post_id, c.comment_author, c.comment_author_email, c.comment_date, c.comment_content ' \
      "FROM wp_comments c WHERE c.comment_type <> 'pingback' and c.comment_approved = 1"

seo_sql = 'select p.post_id, p.meta_value ' \
        "FROM wp_postmeta p WHERE meta_key = '_yoast_wpseo_metadesc'"

uncategorized_id = get_uncategorized_id()

def sql(sql):
    connection = pymysql.connect(host=MYSQL_HOST, user=MYSQL_USERNAME, password=MYSQL_PASSWORD, db=MYSQL_DATABASE)
    cursor = connection.cursor()
    cursor.execute(sql)
    results = cursor.fetchall()
    cursor.close()
    connection.close()
    return results

post_results = sql(post_sql)
'''
for result in post_results:
    wp_post = WpPost(*result)
    guid_index = wp_post.guid.find('?p=')
    wordpress_guid = wp_post.guid[guid_index + 3:]

    r = requests.get(wp_post.guid)
    wordpress_url = r.url

    wordpress_prefix = 'http://matthewmoisen.com/blog/'
    wordpress_url = r.url[len(wordpress_prefix):]

    print wp_post.title, wordpress_guid, wordpress_url
'''

wordpresses = []
posts = {}
comments = []
images = {}
for result in post_results:
    wp_post = WpPost(*result)

    guid_index = wp_post.guid.find('?p=')
    wordpress_guid = wp_post.guid[guid_index + 3:]
    wordpresses.append(Wordpress(type='guid', val=wordpress_guid, redirect=wp_post.post_name))

    try:
        r = requests.get(wp_post.guid)
    except requests.RequestException as ex:
        print "EXCEPTION ", ex.message
        print "guid was ", wp_post.guid
        raise

    wordpress_prefix = 'http://matthewmoisen.com/blog/'
    wordpress_url = r.url[len(wordpress_prefix):]
    wordpresses.append(Wordpress(type='url', val=wordpress_url, redirect=wp_post.post_name))


    title = ''.join([i if ord(i) < 128 else ' ' for i in wp_post.title])

    content = ''.join([i if ord(i) < 128 else ' ' for i in wp_post.content])
    content = content.replace('\r\n', '<br>')
    html = BeautifulSoup(content)
    for img in html.findAll('img'):
        new_path = os.path.join(app.static_url_path, 'images', os.path.split(img['src'])[1])
        images[img['src']] = new_path
        content = content.replace(img['src'], new_path)

    content = html2text.html2text(content)
    content = content.replace('/wp-\n', '/wp-')
    content = content.replace('/blog\n', '/blog')

    post = Post(user_id=user.id, title=title, content=content, url_name=wp_post.post_name,
                description = title,
                creation_date=wp_post.creation_date, last_modified_date=wp_post.last_modified_date, is_published=True,
                category_id=uncategorized_id)


    posts[wp_post.id] = post


db.session.bulk_save_objects(posts.values(), return_defaults=True)

category_posts = []
for p in posts.values():
    category_post = CategoryPost(post_id=p.id, category_id=uncategorized_id)
    category_posts.append(category_post)

db.session.bulk_save_objects(category_posts)

# Download imagees to static folder
s = datetime.now()
for image, redirect in images.iteritems():
    #print title, image, os.path.split(image)[1]
    if image.startswith('data:'):
        content = base64.b64decode(image.replace('data:image/png;base64,', ''))
        file_name = str(uuid.uuid4()) + '.png'
    else:
        if not args.no_image_download:
            r = requests.get(image)
            content = r.content
        file_name = os.path.split(image)[1]

        wordpress_prefix = 'http://matthewmoisen.com/blog/'
        image_url = image[len(wordpress_prefix):]


        wordpress = Wordpress(type='image', val=image_url, redirect=redirect)
        wordpresses.append(wordpress)

    if not args.no_image_download:
        with open(os.path.join(app.config['UPLOAD_FOLDER'], file_name), 'wb') as f:
            f.write(content)
e = datetime.now()

print "time to save images: {}".format(e - s)

db.session.bulk_save_objects(wordpresses)

for result in sql(seo_sql):
    wp_meta = WpMeta(*result)
    try:
        posts[wp_meta.post_id].description = wp_meta.meta_value
    except KeyError as ex:
        print ex

db.session.bulk_save_objects(posts.values(), return_defaults=True)


for result in sql(comment_sql):
    wp_comment = WpComment(*result)
    content = ''.join([i if ord(i) < 128 else ' ' for i in wp_comment.content])
    content = content.replace('\r\n', '<br>')
    content = html2text.html2text(content)
    comment = Comment(email=wp_comment.email, name=wp_comment.name, content=content, creation_date=wp_comment.creation_date, is_approved=True)
    comment.post_id = posts[wp_comment.post_id].id
    comments.append(comment)

db.session.bulk_save_objects(comments, return_defaults=True)
db.session.commit()