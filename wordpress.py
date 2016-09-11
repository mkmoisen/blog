import html2text
import pymysql
from blog.local_settings import MYSQL_DATABASE, MYSQL_HOST, MYSQL_PASSWORD, MYSQL_PORT, MYSQL_USERNAME
from blog.models import User, Post, Comment
from blog import db, app
from collections import defaultdict, namedtuple
from BeautifulSoup import BeautifulSoup
import os
import requests
from datetime import datetime
import uuid
import base64

user = db.session.query(User).one()

WpPost = namedtuple('WpPost', ('id', 'title', 'content', 'creation_date', 'last_modified_date', 'post_name'))
WpComment = namedtuple('WpComment', ('post_id', 'name', 'email', 'creation_date', 'content'))
WpMeta = namedtuple('WpMeta', ('post_id', 'meta_value'))

post_sql = 'select p.id, p.post_title, p.post_content, p.post_date, p.post_modified, p.post_name  ' \
      "FROM wp_posts p WHERE 1=1 AND p.post_status = 'publish'"

comment_sql = 'select c.comment_post_id, c.comment_author, c.comment_author_email, c.comment_date, c.comment_content ' \
      "FROM wp_comments c WHERE c.comment_type <> 'pingback' and c.comment_approved = 1"

seo_sql = 'select p.post_id, p.meta_value ' \
        "FROM wp_postmeta p WHERE meta_key = '_yoast_wpseo_metadesc'"

def sql(sql):
    connection = pymysql.connect(host=MYSQL_HOST, user=MYSQL_USERNAME, password=MYSQL_PASSWORD, db=MYSQL_DATABASE)
    cursor = connection.cursor()
    cursor.execute(sql)
    results = cursor.fetchall()
    cursor.close()
    connection.close()
    return results

post_results = sql(post_sql)

posts = {}
comments = []
images = {}
for result in post_results:
    wp_post = WpPost(*result)
    title = ''.join([i if ord(i) < 128 else ' ' for i in wp_post.title])
    content = ''.join([i if ord(i) < 128 else ' ' for i in wp_post.content])
    #content = unicode(content)
    content = content.replace('\r\n', '<br>')
    html = BeautifulSoup(content)
    for img in html.findAll('img'):
        images[img['src']] = wp_post.title
        new_path = os.path.join(app.static_url_path, 'images', os.path.split(img['src'])[1])
        content = content.replace(img['src'], new_path)

    content = html2text.html2text(content)
    content = content.replace('/wp-\n', '/wp-')
    content = content.replace('/blog\n', '/blog')
    post = Post(user_id=user.id, title=title, content=content, url_name=wp_post.post_name,
                description = title,
                creation_date=wp_post.creation_date, last_modified_date=wp_post.last_modified_date, is_published=True)
    posts[wp_post.id] = post


db.session.bulk_save_objects(posts.values(), return_defaults=True)

# Download imagees to static folder
s = datetime.now()
for image, title in images.iteritems():
    #print title, image, os.path.split(image)[1]
    if image.startswith('data:'):
        content = base64.b64decode(image.replace('data:image/png;base64,', ''))
        file_name = str(uuid.uuid4()) + '.png'
    else:
        r = requests.get(image)
        content = r.content
        file_name = os.path.split(image)[1]
    with open(os.path.join(app.config['UPLOAD_FOLDER'], file_name), 'wb') as f:
        f.write(content)
e = datetime.now()

print "time to save images: {}".format(e - s)

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