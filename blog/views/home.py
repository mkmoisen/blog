# -*- coding: utf-8 -*-
from blog.models import *
from blog import app
from blog import db
from . import  date_format
from flask import jsonify, request, url_for, redirect, g, session, render_template, flash, abort
from datetime import datetime
from sqlalchemy.exc import SQLAlchemyError, IntegrityError
from sqlalchemy.orm.exc import NoResultFound
from werkzeug.exceptions import BadRequest
from functools import wraps
from . import try_except, UserError, ServerError
from blog.models import *
import markdown
from passlib.hash import sha256_crypt
from sqlalchemy import desc
import re
import validate_email
from werkzeug.utils import secure_filename
import os
from sqlalchemy.sql import func
from sqlalchemy.sql.expression import literal_column
from BeautifulSoup import BeautifulSoup

def login_required(f):
    @wraps(f)
    def _login_required(*args, **kwargs):
        if not session or 'logged_in' not in session or not session['logged_in']:
            return redirect(url_for('admin_login'))

        return f(*args, **kwargs)

    return _login_required


@app.route('/blog/<url_name>/', methods=['GET'])
def get_post_by_name(url_name):
    p = db.session.query(Post).filter_by(url_name=url_name).one()

    return post(p.id)

from sqlalchemy import and_



@app.route('/', methods=['GET'])
@app.route('/home/', methods=['GET'])
@app.route('/post/', methods=['GET'])
@try_except()
def home():
    '''
    Grab all published posts and display for user along with category
    '''
    posts = db.session.query(Post, Category) \
        .outerjoin(CategoryPost, and_(Post.id == CategoryPost.post_id, Post.category_id == CategoryPost.category_id)) \
        .outerjoin(Category) \
        .filter(Post.is_published == True) \
        .order_by(Post.creation_date.desc())\
        .all()

    is_admin = check_admin_status()

    posts = [
        {
            'title': p.title,
            'post_id': p.id,
            'url_name': p.url_name,
            'category': c.name if c is not None else 'Uncategorized',
            'category_id': c.id if c is not None else 0

        }
        for p, c in posts
    ]
    return render_template('home.html', posts=posts, is_admin=is_admin)

@app.route('/admin/post/', methods=['GET'])
@try_except()
@login_required
def admin_post():
    posts = db.session.query(Post, Category).outerjoin(Category) \
        .order_by(Post.is_published.asc()) \
        .order_by(Post.creation_date.desc())\
        .all()

    posts = [
        {
            'title': p.title,
            'category': c.name if c is not None else 'Uncategorized',
            'post_id': p.id,
            'is_published': p.is_published,
            'url_name': p.url_name,
            'category_id': c.id if c is not None else 0
        }
        for p, c in posts
    ]

    return render_template('admin-post.html', posts=posts)


'''
def print_tree(tree, depth=0):
    for child in tree:
        print '    ' * depth + child['name']
        print_tree(child['children'], depth + 1)


def iter_tree(tree, depth=0):
    for child in tree:
        yield '    ' * depth + child['name']
        for i in iter_tree(child['children'], depth + 1):
            yield i

def _append_tree(category, tree):
    tree.append({'id': category.id, 'name': category.name, 'children': []})

def add_node(category, tree):
    if category.parent_id is None:
        _append_tree(category, tree)
        return 1
    for child in tree:
        if category.parent_id == child['id']:
            _append_tree(category, child['children'])
            return 1
        if add_node(category, child['children']):
            return 1
    return 0
'''



def print_tree(tree, depth=0):
    for child in tree:
        print '    ' * depth + child['category'].name
        print_tree(child['children'], depth + 1)


def iter_tree(tree, depth=0):
    for child in tree:
        yield depth, child['category']
        for i in iter_tree(child['children'], depth + 1):
            yield i

def _append_tree(category, tree, parent=None):
    tree.append({'parent': parent, 'category': category, 'children': []})

def _add_node(category, tree, back=None):
    if back is None:
        back = {}
    for child in tree:
        if category.parent_id == child['category'].id:
            _append_tree(category, child['children'], child)
            back[category.id] = child['category']
            return 1
        if _add_node(category, child['children'], back):
            return 1
    return 0

def add_node(category, tree, back=None):
    if back is None:
        back = {}
    if category.parent_id is None:
        _append_tree(category, tree)
        back[category.id] = None
        return 1

    if not _add_node(category, tree, back):
        # This means that the order_by clause was incorrect on the category query
        # and that the parents have not been added before the children
        # TODO actually should I be relying on parent_id to be ordered correctly???
        raise ValueError("categories parent id not found for {}".format(category))

def lol(back, category):
    yield category
    if back[category.id] is not None:
        for i in lol(back, back[category.id]):
            yield i

def _find_ascendants(back, category):
    yield category
    if back[category.id] is not None:
        for i in _find_ascendants(back, back[category.id]):
            yield i

def find_ascendants(back, category):
    if category.parent_id is None:
        return
    for i in _find_ascendants(back, back[category.id]):
        yield i





@app.route('/category/', methods=['GET'])
@try_except()
def category():
    '''
    Returns a list of categories and the associated post count within each
    '''

    '''
    tree = []
    categories = db.session.query(Category).order_by(Category.parent_id).all()
    for category in categories:
        print category.id, category.name, category.parent_id
        add_node(category, tree)

    print_tree(tree)

    for depth, c in iter_tree(tree):
        print '----' * depth + c.name, c.id

    '''

    categories = db.session.query(Category, func.count(1)) \
            .outerjoin(CategoryPost) \
            .outerjoin(Post) \
            .filter(Post.is_published == True) \
            .group_by(Category.name) \
            .order_by(Category.parent_id)

    categories = db.session.query(Category, func.count(1)) \
        .select_from(Post).outerjoin(CategoryPost).outerjoin(Category) \
        .filter(Post.is_published == True) \
        .group_by(Category) \
        .order_by(Category.parent_id)

    tree = []
    for category, count in categories:
        if category is not None:
            category.count = count
            app.logger.debug(category)
            app.logger.debug("DID IT WORK LOL {}".format(add_node(category, tree)))

    print_tree(tree)

    app.logger.debug(tree)

    for depth, cat in iter_tree(tree):
        print cat

    categories = [
        {
            'depth': depth,
            'name': category.name,
            'category_id': category.id,
            'count': category.count
        }
        for depth, category in iter_tree(tree)
    ]

    app.logger.debug("Categories is {}".format(categories))

    uncategorized = db.session.query(func.count(1)).select_from(Post).outerjoin(CategoryPost) \
        .filter(CategoryPost.id == None).filter(Post.is_published == True).one()

    if uncategorized[0]:
        categories.append({
            'depth': 0, 'name': 'Uncategorized', 'category_id': 0, 'count': uncategorized[0]
        })


    is_admin = check_admin_status()


    return render_template('category.html', categories=categories, is_admin=is_admin)

@app.route("/projects/", methods=['GET'])
@try_except()
def get_projects():
    category = db.session.query(Category).filter_by(name="Projects").one()
    return category_posts(category.id)


@app.route('/resume/', methods=['GET'])
@try_except()
def resume():
    return get_post_by_name('resume')

@app.route('/category/<int:category_id>/', methods=['GET'])
@try_except()
def category_posts(category_id):
    # Uncategorized have category_id of Null. Because strings cannot be passed, make sure to pass a 0 instead

    if category_id == 0:
        category_id = None
        category_name = "Uncategorized"
    else:
        category = db.session.query(Category).filter_by(id=category_id).one()
        category_name = category.name

    posts = db.session.query(Post).join(CategoryPost) \
        .filter(CategoryPost.category_id == category_id) \
        .filter(Post.is_published == True) \
        .order_by(desc(Post.creation_date)) \
        .all()

    is_admin = check_admin_status()

    posts = [
        {
            'title': p.title,
            'post_id': p.id
        }
        for p in posts
    ]

    return render_template('category-posts.html', posts=posts, category_name=category_name, category_id=category_id,
                           is_admin=is_admin)

@app.route('/admin/', methods=['GET'])
@try_except()
def admin():
    if 'logged_in' not in session or not session['logged_in']:
        return redirect(url_for('admin_login'))

    return render_template('admin.html')

@app.route('/admin/create/', methods=['GET','POST'])
@try_except()
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
    db.session.flush()

    # Create temporary Resume post
    dt = datetime.now()
    post = Post(user_id=user.id, title=u"Résumé", url_name='resume', description=u'Résumé for Matthew Moisen',
                content=u'My Résumé', is_published=True, creation_date=dt, last_modified_date=dt,
                is_commenting_disabled=True)
    db.session.add(post)

    # Create Projects Category
    category = Category(name='Projects')
    db.session.add(category)

    db.session.commit()

    return redirect(url_for('admin_login'))

@app.route('/admin/login/', methods=['GET', 'POST'])
@try_except()
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

def get_category_tree(back=None):
    if back is None:
        back = {}
    tree = []
    for category in db.session.query(Category).order_by(Category.parent_id):
        add_node(category, tree, back)

    return tree

def get_categories(back=None):

    tree = get_category_tree()

    return [
        {
            'id': category.id,
            'name': category.name,
            'depth': depth
        }
        for depth, category in iter_tree(tree)
    ]




@app.route('/admin/category/', methods=['GET', 'POST'])
@app.route('/admin/category/<int:category_id>/', methods=['GET','POST'])
@try_except()
@login_required
def admin_category_create(category_id=None):
    category_id = '' if category_id is None else category_id
    name = ''
    parent_id = session.pop('parent_id', None)
    if parent_id is None:
        parent_id = ''

    categories = get_categories()

    if request.method == 'GET':
        if category_id != '':
            # This is for updates
            category = db.session.query(Category).filter_by(id=category_id).one()
            name = category.name

        return render_template('admin-category-create.html',
                               name=name,
                               category_id=category_id,
                               categories=categories,
                               parent_id=parent_id)

    elif request.method == 'POST':
        app.logger.debug("FORM IS {}".format(request.form))

        category_id = request.form['category_id']
        name = request.form['category_name']
        parent_id = request.form['category_parent_id']
        try:
            parent_id = int(parent_id)
        except ValueError:
            parent_id = None

        if category_id == '':
            category = Category()
        else:
            category = db.session.query(Category).filter_by(id=category_id).one()

        category.name = name
        category.parent_id = parent_id

        db.session.add(category)
        try:
            db.session.commit()
        except IntegrityError as ex:
            flash(ex.message, 'error')
            session['parent_id'] = parent_id
            return redirect(url_for('admin_category_create'), categories=categories)
        else:
            flash("Category '{}' created successfully".format(name), 'success')

        return redirect(url_for('admin_category_create'))



@app.route('/api/upload-image/', methods=['POST'])
@try_except(api=True)
@login_required
def upload_image():
    app.logger.debug(request.files)
    if not request.files:
        raise UserError("File is empty")


    file = request.files['file']

    app.logger.debug("filename is {}".format(file.filename))

    if file.filename is None or file.filename == '':
        raise UserError("Filename is none or empty")

    file_name = secure_filename(file.filename)

    file_path = os.path.join(app.config['UPLOAD_FOLDER'], file_name)

    if os.path.isfile(file_path):
        raise UserError("A file with that name has already been saved")

    try:
        file.save(file_path)
    except IOError as ex:
        raise ServerError("Could not save file: {}".format(ex.message))

    markdown = '\n\n' + '![{file_name}](/static/images/{file_name}) \n'.format(file_name=file_name)

    return jsonify({"markdown": markdown}), 200




@app.route('/admin/post/new/', methods=['GET', 'POST'])
@app.route('/admin/post/<int:post_id>/', methods=['GET','POST'])
@try_except()
@login_required
def admin_post_create(post_id=None):
    def admin_post_create_error(message, title, content, main_category_id, other_category_ids, post_id,
                                is_commenting_disabled):
        flash(message, 'error')
        session['title'] = title
        session['content'] = content
        session['main_category_id'] = main_category_id
        session['other_category_ids'] = other_category_ids
        session['post_id'] = post_id
        session['is_commenting_disabled'] = is_commenting_disabled


    main_category_id = request.args.get('main_category_id', '')
    try:
        main_category_id = int(main_category_id)
    except ValueError:
        main_category_id = ''

    title = session.pop('title', '')
    content = session.pop('content', '')
    main_category_id = session.pop('main_category_id', main_category_id)
    other_category_ids = session.pop('other_category_ids', [])
    url_name = session.pop('url_name', '')
    description = session.pop('url_name', '')
    post_id = '' if post_id is None else post_id
    is_commenting_disabled = session.pop('is_commenting_disabled', False)
    categories = get_categories()

    if request.method == 'GET':

        if post_id != '':
            post = db.session.query(Post).filter_by(id=post_id).one()
            title = post.title
            content = post.content
            url_name = post.url_name
            description = post.description
            post_id = post.id
            main_category_id = post.category_id
            is_commenting_disabled = post.is_commenting_disabled

            other_categories = db.session.query(CategoryPost).filter_by(post_id=post_id).all()
            other_category_ids = [other_category.category_id for other_category in other_categories]

        return render_template('admin-post-create.html',
                               title=title,
                               content=content,
                               post_id=post_id,
                               description=description,
                               url_name=url_name,
                               categories=categories,
                               main_category_id=main_category_id,
                               other_category_ids=other_category_ids,
                               is_commenting_disabled=is_commenting_disabled)

    elif request.method == 'POST':
        app.logger.debug("I AM POST")
        app.logger.debug("FORM IS {}".format(request.form))
        post_id = request.form['post_id']
        title = request.form['post_title']
        content = request.form['post_content']
        main_category_id = request.form['main_category_id']
        # Use request.form.getlist to pull all values from multivalue select list
        # request.form.get only pulls out the first option
        other_category_ids = request.form.getlist('other_category_ids')
        url_name = request.form['url_name']
        description = request.form['description']
        submit = request.form['submit']
        is_commenting_disabled = True if 'is_commenting_disabled' in request.form else False

        app.logger.debug("other_category_ids is {}".format(other_category_ids))

        # Category can be null for an uncategorized post
        if main_category_id == '':
            main_category_id = None
        else:
            main_category_id = int(main_category_id)

        other_category_ids = map(int, other_category_ids)


        app.logger.debug("other_category_ids is {}".format(other_category_ids))

        # If user forgot to select a main category id, pick the first one from other categories
        if other_category_ids and main_category_id is None:
            main_category_id = other_category_ids[0]

        # Make sure to add main_category_id if it wasn't selected in other_category_ids
        #if not other_category_ids and main_category_id is not None:
        if main_category_id is not None and main_category_id not in other_category_ids:
            other_category_ids.append(main_category_id)

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
        post.category_id = main_category_id
        post.user_id = session['user_id']
        post.is_commenting_disabled = is_commenting_disabled

        if url_name == '':
            url_name = re.sub(r'[/:\\.;,?\{}\[\]|]', '', title)
            url_name = ' '.join(url_name.split())
            url_name = url_name.lower().replace(' ', '-')


        if description == '':
            description = title.capitalize()

        post.description = description

        post.url_name = url_name

        if title == '' or content == '':
            admin_post_create_error('Title or content is empty', title, content, main_category_id, other_category_ids,
                                    post_id, is_commenting_disabled)
            return redirect(url_for('admin_post_create'))

        if submit == 'publish':
            post.is_published = True
        elif submit == 'draft':
            post.is_published = False

        db.session.add(post)
        try:
            db.session.flush()
        except SQLAlchemyError as ex:
            app.logger.debug("ERROR {}".format(ex.message))
            admin_post_create_error(ex.message, title, content, main_category_id, other_category_ids,
                                    post_id, is_commenting_disabled)
            return redirect(url_for('admin_post_create'))

        db.session.query(CategoryPost).filter_by(post_id=post.id).delete()


        # other_category_ids has all the other_category_ids AND the main_category_id in it now
        all_category_ids = set(other_category_ids)
        back = {}
        get_category_tree(back)
        other_categories = db.session.query(Category).filter(Category.id.in_(other_category_ids)).all()
        for other_category in other_categories:
            for ascendant in find_ascendants(back, other_category):
                all_category_ids.add(ascendant.id)

        category_posts = [CategoryPost(category_id=category_id, post_id=post.id) for category_id in all_category_ids]
        if category_posts:
            db.session.bulk_save_objects(category_posts)

        try:
            db.session.commit()
        except SQLAlchemyError as ex:
            app.logger.debug("ERROR {}".format(ex.message))
            admin_post_create_error(ex.message, title, content, main_category_id, other_category_ids,
                                    post_id, is_commenting_disabled)
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

@app.route('/admin/post/<int:post_id>/publish/', methods=['GET'])
@try_except()
def mark_post_as_published(post_id):
    last_url = request.args.get('last_url', 'post')

    post = db.session.query(Post).filter_by(id=post_id).one()
    if not post.is_published:
        post.is_published = True
        db.session.add(post)
        db.session.commit()

    return redirect(url_for(last_url, post_id=post_id))

@app.route('/admin/post/<int:post_id>/draft/', methods=['GET'])
@try_except()
def mark_post_as_draft(post_id):
    post = db.session.query(Post).filter_by(id=post_id).one()

    last_url = request.args.get('last_url', 'post')

    if post.is_published:
        post.is_published = False
        db.session.add(post)
        db.session.commit()

    return redirect(url_for(last_url, post_id=post_id))

def check_admin_status():
    return 'is_admin' in session and session['is_admin']

@app.route('/post/<int:post_id>/', methods=['GET'])
@try_except()
def post(post_id):
    post = db.session.query(Post).filter_by(id=post_id).one()

    is_admin = check_admin_status()

    # Only admin should be able to view drafts
    if not post.is_published:
        if not is_admin:
            abort(404)

    title = post.title
    # markdown should be applied when comment is created
    content = markdown.markdown(post.content)
    post_id = post.id
    is_published = post.is_published
    url_name = post.url_name
    description = post.description
    is_commenting_disabled = post.is_commenting_disabled


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
                           is_admin=is_admin,
                           title=title,
                           content=content,
                           post_id=post_id,
                           url_name=url_name,
                           is_published=is_published,
                           description=description,
                           comment_name=comment_name,
                           comment_content=comment_content,
                           comment_email=comment_email,
                           comments=comments,
                           is_commenting_disabled=is_commenting_disabled,
                           spam_operator=spam['operator'],
                           spam_word=spam['word'],
                           spam_answer=spam['answer'])


def check_for_urls(text):
    # http://stackoverflow.com/a/6883094/1391717
    return re.findall(r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\(\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+', text)

@app.route('/post/<int:post_id>/comment/', methods=['POST'])
@try_except()
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

    # Sanitize Name and Comment of any html tabgs
    soups = (BeautifulSoup(name), BeautifulSoup(email), BeautifulSoup(content))
    name, email, content = (''.join(soup.findAll(text=True)) for soup in soups)

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
@try_except()
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
@try_except()
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
@try_except()
@login_required
def admin_comment_approve(comment_id):
    comment = db.session.query(Comment).filter_by(id=comment_id).one()
    comment.is_approved = True
    db.session.add(comment)
    db.session.commit()

    return redirect(url_for('admin_comment_queue'))

@app.route('/admin/comment/<int:comment_id>/delete/')
@try_except()
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

