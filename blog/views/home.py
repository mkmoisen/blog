from blog.models import *
from blog import app
from blog import db
from . import UserError, ServerError, date_format
from flask import jsonify, request, url_for, redirect, g, session, render_template, flash
from datetime import datetime
from sqlalchemy.exc import SQLAlchemyError, IntegrityError
from sqlalchemy.orm.exc import NoResultFound
from werkzeug.exceptions import BadRequest
from functools import wraps
from . import try_except
from blog.models import *
import markdown
from passlib.hash import sha256_crypt
from sqlalchemy import desc
import re
import validate_email
from werkzeug.utils import secure_filename
import os

def login_required(f):
    @wraps(f)
    def _login_required(*args, **kwargs):
        if not session or not 'logged_in' in session or not session['logged_in']:
            return redirect(url_for('admin_login'))

        return f(*args, **kwargs)

    return _login_required


@app.route('/', methods=['GET'])
@app.route('/home/', methods=['GET'])
def home():
    posts = db.session.query(Post, Category).outerjoin(Category) \
        .filter(Post.is_published == True) \
        .order_by(desc(Post.creation_date))\
        .all()

    posts = [
        {
            'title': p.title,
            'category': c.name if c is not None else 'Uncategorized',
            'post_id': p.id,
            'category_id': c.id if c is not None else 0
        }
        for p, c in posts
    ]
    return render_template('home.html', posts=posts)

@app.route('/category/', methods=['GET'])
def category():
    categories = db.session.query(Category) \
        .order_by(Category.name) \
        .all()

    categories = [
        {
            'name': category.name,
            'category_id': category.id
        }
        for category in categories
    ]

    return render_template('category.html', categories=categories)

@app.route('/category/<int:category_id>/', methods=['GET'])
def category_posts(category_id):
    # Uncategorized have category_id of Null. Because strings cannot be passed, make sure to pass a 0 instead

    if category_id == 0:
        category_id = None
        category_name = "Uncategorized"
    else:
        category = db.session.query(Category).filter_by(id=category_id).one()
        category_name = category.name

    posts = db.session.query(Post) \
        .filter_by(category_id=category_id) \
        .filter_by(is_published=True) \
        .order_by(desc(Post.creation_date)) \
        .all()

    posts = [
        {
            'title': p.title,
            'post_id': p.id
        }
        for p in posts
    ]

    return render_template('category-posts.html', posts=posts, category_name=category_name)

@app.route('/admin/', methods=['GET'])
def admin():
    if 'logged_in' not in session or not session['logged_in']:
        return redirect(url_for('admin_login'))

    return render_template('admin.html')

@app.route('/admin/create/', methods=['GET','POST'])
def admin_create():
    if request.method == 'GET':
        try:
            db.session.query(User).one()
        except NoResultFound:
            pass
        else:
            # There is already an Admin, redirect to login page
            return redirect(url_for('admin_login'))

        spam = math_spam()

        first_name = session.pop('first_name', '')
        last_name = session.pop('last_name', '')
        email = session.pop('email', '')

        return render_template('admin-create.html',
                               spam_operator=spam['operator'],
                               spam_word=spam['word'],
                               spam_answer=spam['answer'],
                               first_name=first_name,
                               last_name=last_name,
                               email=email)

    first_name = request.form['first_name']
    last_name = request.form['last_name']
    email = request.form['email']
    password = request.form['password']
    input_spam_check = request.form['spam_check']

    resubmit = spam_check(input_spam_check)

    if first_name == '' or last_name == '' or email == '' or password == '':
        resubmit = True
        flash("First name, last name, email, and password may not be empty", 'error')

    if resubmit:
        session['first_name'] = first_name
        session['last_name'] = last_name
        session['email'] = email
        return redirect(url_for('admin_create'))

    password = sha256_crypt.encrypt(password)

    user = User(first_name=first_name, last_name=last_name, email=email, password=password)
    db.session.add(user)
    db.session.commit()

    return redirect(url_for('admin_login'))

@app.route('/admin/login/', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'GET':
        try:
            db.session.query(User).one()
        except NoResultFound:
            # There is no admins, redirect user to sign on page
            return redirect(url_for('admin_create'))

        spam = math_spam()
        email = session.pop('email', '')

        return render_template('admin-login.html',
                               spam_operator=spam['operator'],
                               spam_word=spam['word'],
                               spam_answer=spam['answer'],
                               email=email)

    email = request.form['email']
    password = request.form['password']
    input_spam_check = request.form['spam_check']

    resubmit = spam_check(input_spam_check)

    if not resubmit:

        try:
            user = db.session.query(User).filter_by(email=email).one()
        except NoResultFound:
            app.logger.debug("No user found with this email {}".format(email))
            resubmit = True
        else:
            resubmit = not sha256_crypt.verify(password, user.password)
            app.logger.debug("Verify was {}".format(resubmit))

    if resubmit:
        session['logged_in'] = False
        session['email'] = email
        flash("Failed to login", 'error')
    else:
        session['logged_in'] = True
        session['is_admin'] = user.is_admin
        session['user_id'] = user.id

    # TODO add spam checker

    return redirect(url_for('admin'))

def get_categories():
    categories = db.session.query(Category).all()
    return [cat.json for cat in categories]


@app.route('/admin/category/', methods=['GET', 'POST'])
@app.route('/admin/category/<int:category_id>/', methods=['GET','POST'])
@login_required
def admin_category_create(category_id=None):
    category_id = '' if category_id is None else category_id
    name = ''

    if request.method == 'GET':
        if category_id != '':
            # This is for updates
            category = db.session.query(Category).filter_by(id=category_id).one()
            name = category.name

        return render_template('admin-category-create.html',
                               name=name,
                               category_id=category_id)

    elif request.method == 'POST':
        app.logger.debug("FORM IS {}".format(request.form))

        category_id = request.form['category_id']
        name = request.form['category_name']

        if category_id == '':
            category = Category()
        else:
            category = db.session.query(Category).filter_by(id=category_id).one()

        category.name = name

        db.session.add(category)
        try:
            db.session.commit()
        except IntegrityError as ex:
            flash(ex.message, 'error')
            return redirect(url_for('admin_category_create'))
        else:
            flash("Category '{}' created successfully".format(name), 'success')

        return redirect(url_for('admin_category_create'))


@app.route('/admin/post/upload-image/', methods=['POST'])
def admin_post_upload_image():
    app.logger.debug("request.files is {}".format(request.files))
    if 'file' in request.files:
        file = request.files['file']

        app.logger.debug("filename is {}".format(file.filename))

        if file.filename == '':
            flash('No selected file', 'error')

        file_name = secure_filename(file.filename)
        file.save(os.path.join(app.config['UPLOAD_FOLDER'], file_name))

        app.logger.debug("file was saved")

        return redirect(url_for('admin_post_create', post_id=post.id))




    return redirect(url_for('admin_post_create', post_id=post_id))


@app.route('/admin/post/', methods=['GET', 'POST'])
@app.route('/admin/post/<int:post_id>/', methods=['GET','POST'])
@login_required
def admin_post_create(post_id=None):
    title = session.pop('title', '')
    content = session.pop('content', '')
    category_id = session.pop('category_id', '')
    post_id = '' if post_id is None else post_id
    categories = get_categories()

    if request.method == 'GET':
        app.logger.debug("I AM GET")
        if post_id != '':
            post = db.session.query(Post).filter_by(id=post_id).one()
            title = post.title
            content = post.content
            post_id = post.id
            category_id = post.category_id

        return render_template('admin-post-create.html',
                       title=title,
                       content=content,
                       post_id=post_id,
                       categories=categories,
                       category_id=category_id)

    elif request.method == 'POST':
        app.logger.debug("I AM POST")
        app.logger.debug("FORM IS {}".format(request.form))
        post_id = request.form['post_id']
        title = request.form['post_title']
        content = request.form['post_content']
        category_id = request.form['category_id']

        if category_id == '':
            category_id = None
        else:
            category_id = int(category_id)

        dt = datetime.now()
        if post_id == '':
            # new post
            post = Post(creation_date=dt)  # title=title, content=content, creation_date=dt, last_modified_date=dt, category_id=category_id)
        else:
            post = db.session.query(Post).filter_by(id=post_id).one()

        post.title = title
        # What if I want to legitimately use '\r\n' ?
        post.content = content.replace('\r\n', '\n')
        post.last_modified_date = dt
        post.category_id = category_id
        post.user_id = session['user_id']

        db.session.add(post)
        try:
            db.session.commit()
        except SQLAlchemyError as ex:
            app.logger.debug("ERROR {}".format(ex.message))
            flash(ex.message, 'error')
            session['title'] = title
            session['content'] = content
            session['category_id'] = category_id
            session['post_id'] = post_id
            return redirect(url_for('admin_post_create'))

        app.logger.debug("File in request.files? {}".format('file' in request.files))
        app.logger.debug("request.files is {}".format(request.files))
        if 'file' in request.files:
            file = request.files['file']

            app.logger.debug("filename is {}".format(file.filename))

            if file.filename is not None and file.filename != '':
                file_name = secure_filename(file.filename)
                file.save(os.path.join(app.config['UPLOAD_FOLDER'], file_name))

                app.logger.debug("file was saved")

                post.content += '\n' + '![{file_name}](/static/{file_name}) \n'.format(file_name=file_name)
                db.session.add(post)
                db.session.commit()

                return redirect(url_for('admin_post_create', post_id=post.id))

        return redirect(url_for('post', post_id=post.id))




@app.route('/post/<int:post_id>/', methods=['GET'])
def post(post_id):
    post = db.session.query(Post).filter_by(id=post_id).one()
    title = post.title
    # markdown should be applied when comment is created
    content = markdown.markdown(post.content)
    post_id = post.id


    comment_name = session.pop('comment_name', '')
    comment_content = session.pop('comment_content', '')
    comment_email = session.pop('comment_email', '')

    comments = db.session.query(Comment).filter_by(post_id=post_id)
    comments = comments.filter(Comment.is_approved == True)
    comments = comments.all()

    # Todo sort by creation_date desc

    comments = [
        {
            'name': comment.name,
            'content': comment.content,
            'creation_date': comment.creation_date
        }
        for comment in comments
    ]

    spam = math_spam()

    return render_template('post.html',
                           title=title,
                           content=content,
                           post_id=post_id,
                           comment_name=comment_name,
                           comment_content=comment_content,
                           comment_email=comment_email,
                           comments=comments,
                           spam_operator=spam['operator'],
                           spam_word=spam['word'],
                           spam_answer=spam['answer'])


def check_for_urls(text):
    # http://stackoverflow.com/a/6883094/1391717
    return re.findall(r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\(\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+', text)

@app.route('/post/<int:post_id>/comment/', methods=['POST'])
def post_comment(post_id):

    post = db.session.query(Post).filter_by(id=post_id).one()

    app.logger.debug("FORM IS {}".format(request.form))
    name = request.form['comment_name']
    email = request.form['comment_email']
    content = request.form['comment_content']
    input_spam_check = request.form['spam_check']

    resubmit = spam_check(input_spam_check)

    urls = check_for_urls(content)
    if urls:
        flash("URLs are not permitted in comments.", 'error')
        resubmit = True

    urls = check_for_urls(name)
    if urls:
        flash("URLs are not permitted in name.", 'error')
        resubmit = True

    if email != '':
        if not validate_email.validate_email(email):
            flash("Email is invalid", 'error')
            resubmit = True

    if name == '' or content == '':
        flash("Name or content is empty", 'error')
        resubmit = True

    if resubmit:
        session['comment_name'] = name
        session['comment_email'] = email
        session['comment_content'] = content
        return redirect(url_for('post', post_id=post_id))



    creation_date = datetime.now()

    comment = Comment(post_id=post_id, name=name, email=email, content=content, creation_date=creation_date)
    db.session.add(comment)
    db.session.commit()

    flash("Comment has been submitted to the approval queue successfully", 'success')


    return redirect(url_for('post', post_id=post_id))


def comment_json(q):
    comments = [
        {
            'name': c.name,
            'email': c.email,
            'content': c.content,
            'id': c.id,
            'post_id': p.id,
            'post_title': p.title
        }
        for c, p in q
    ]
    return comments

@app.route('/admin/comment/<int:comment_id>/', methods=['GET', 'POST'])
@login_required
def admin_comment(comment_id):
    comment = db.session.query(Comment).filter_by(id=comment_id).one()

    if request.method == 'GET':
        comment_id = comment.id
        name = session.pop("comment_name", comment.name)
        email = session.pop("comment_email", comment.email)
        content = session.pop("comment_content", comment.content)

        return render_template('admin-comment-create.html',
                               name=name,
                               email=email,
                               content=content,
                               comment_id=comment_id)

    app.logger.debug("FORM IS {}".format(request.form))

    name = request.form['comment_name']
    email = request.form['comment_email']
    content = request.form['comment_content']

    if name == '' or content == '':
        flash("Name or content is empty")
        session['comment_name'] = name
        session['comment_email'] = email
        session['comment_content'] = content
        return redirect(url_for('admin_comment'))

    comment.name = name
    comment.email = email
    comment.content = content

    db.session.add(comment)
    db.session.commit()

    return redirect(url_for('admin_comment_queue'))





@app.route('/admin/comment/queue/', methods=['GET'])
@login_required
def admin_comment_queue():
    queued_comments = db.session.query(Comment, Post).join(Post).filter(Comment.is_approved == False).all()
    queued_comments = comment_json(queued_comments)
    queued_comments_count = len(queued_comments)

    approved_comments = db.session.query(Comment, Post).join(Post).filter(Comment.is_approved == True).all()
    approved_comments = comment_json(approved_comments)
    approved_comments_count = len(approved_comments)

    return render_template('admin-comment-queue.html', queued_comments=queued_comments, approved_comments=approved_comments,
                           queued_comments_count=queued_comments_count, approved_comments_count=approved_comments_count)

@app.route('/admin/comment/<int:comment_id>/approve/')
@login_required
def admin_comment_approve(comment_id):
    comment = db.session.query(Comment).filter_by(id=comment_id).one()
    comment.is_approved = True
    db.session.add(comment)
    db.session.commit()

    return redirect(url_for('admin_comment_queue'))

@app.route('/admin/comment/<int:comment_id>/delete/')
@login_required
def admin_comment_delete(comment_id):
    comment = db.session.query(Comment).filter_by(id=comment_id).one()
    db.session.delete(comment)
    db.session.commit()

    return redirect(url_for('admin_comment_queue'))








number_words = {
    1: 'one',
    2: 'two',
    3: 'three',
    4: 'four',
    5: 'five',
    6: 'six',
    7: 'seven',
    8: 'eight',
    9: 'nine',
    10: 'ten'
}
operators = ['+', '-', '*']
import random
def math_spam():
    number = number_words.keys()[random.randrange(1, len(number_words) + 1) - 1]
    number_to_word = number_words.keys()[random.randrange(1, len(number_words) + 1) - 1]
    word = number_words[number_to_word]

    operator = random.choice(operators)

    answer = eval('{} {} {}'.format(number, operator, number_to_word))

    session['spam_check'] = number

    return {
        'operator': operator,
        'word': word,
        'answer': answer
    }


def spam_check(input_spam_check):
    resubmit = False

    try:
        input_spam_check = int(input_spam_check)
    except ValueError as ex:
        flash("Enter a number, not a string, in humanity check", 'error')
        resubmit = True

    if not resubmit and 'spam_check' not in session:
        app.logger.debug("spam_check not in session")
        flash("Please try humanity check again", 'error')
        resubmit = True

    original_spam_check = session.pop('spam_check')
    app.logger.debug("original_spam_check is {}".format(original_spam_check))
    if not resubmit and not original_spam_check == input_spam_check:
        app.logger.debug("spam check differs")
        flash("Please try humanity check again", 'error')
        resubmit = True

    return resubmit

