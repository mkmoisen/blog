import html2text
import pymysql
from blog.local_settings import MYSQL_DATABASE, MYSQL_HOST, MYSQL_PASSWORD, MYSQL_PORT, MYSQL_USERNAME
from blog.models import User, Post, Comment
from blog import db
from collections import defaultdict, namedtuple
user = db.session.query(User).one()

WpPost = namedtuple('WpPost', ('id', 'title', 'content', 'creation_date', 'last_modified_date'))
WpComment = namedtuple('WpComment', ('post_id', 'name', 'email', 'creation_date', 'content'))

post_sql = 'select p.id, p.post_title, p.post_content, p.post_date, p.post_modified  ' \
      "FROM wp_posts p WHERE 1=1 AND p.post_status = 'publish'"

comment_sql = 'select c.comment_post_id, c.comment_author, c.comment_author_email, c.comment_date, c.comment_content ' \
      "FROM wp_comments c WHERE c.comment_type <> 'pingback' and c.comment_approved = 1"

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
for result in post_results:
    wp_post = WpPost(*result)
    title = ''.join([i if ord(i) < 128 else ' ' for i in wp_post.title])
    content = ''.join([i if ord(i) < 128 else ' ' for i in wp_post.content])
    #content = unicode(content)
    content = content.replace('\r\n', '<br>')
    content = html2text.html2text(content)
    content = content.replace('/wp-\n', '/wp-')
    content = content.replace('/blog\n', '/blog')
    post = Post(user_id=user.id, title=title, content=content, creation_date=wp_post.creation_date, last_modified_date=wp_post.last_modified_date, is_published=True)
    posts[wp_post.id] = post


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