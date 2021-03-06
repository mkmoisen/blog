# -*- coding: utf-8 -*-
from blog.models import *
from blog import app
from blog import db
from . import  date_format
from flask import jsonify, request, url_for, redirect, g, session, render_template, flash, abort
from datetime import datetime
from sqlalchemy.exc import SQLAlchemyError, IntegrityError
from sqlalchemy.orm.exc import NoResultFound
from functools import wraps
from . import try_except, UserError, ServerError, check_admin_status, csrf
from blog.models import *
import markdown
from passlib.hash import sha256_crypt
from sqlalchemy import desc
import re
import validate_email
from werkzeug.utils import secure_filename
import os
from sqlalchemy.sql import func
from bs4 import BeautifulSoup
import requests
import uuid
import random
from xml.etree import ElementTree
from sqlalchemy import or_
import base64
from PIL import Image
import io


def login_required(f):
    @wraps(f)
    def _login_required(*args, **kwargs):
        if not session or 'logged_in' not in session or not session['logged_in']:
            return redirect(url_for('admin_login'))

        return f(*args, **kwargs)

    return _login_required


def get_uncategorized_id():
    uncategorized = db.session.query(Category).filter_by(name='Uncategorized').one()
    return uncategorized.id


@app.route('/blog/')
@try_except()
def blog():
    if 'p' not in request.args:
        return home()

    # This must be a old wordpress URL
    wordpress = db.session.query(Wordpress).filter_by(type='guid').filter_by(val=request.args['p']).one()
    #p = db.session.query(Post).filter_by(wordpress_guid=request.args['p']).one()
    url_name = wordpress.redirect

    return redirect(url_for('get_post_by_name', url_name=url_name), 301)


@app.route('/blog/<first_cat>/<second_cat>/<url_name>/', methods=['GET'])
@try_except()
def wordpress_full_url(first_cat, second_cat, url_name):
    wordpress_url = first_cat + '/' + second_cat + '/' + url_name + '/'
    wordpress = db.session.query(Wordpress).filter_by(type='url').filter_by(val=wordpress_url).one()
    url_name = wordpress.redirect
    return redirect(url_for('get_post_by_name', url_name=url_name), 301)


@app.route('/blog/wp-content/uploads/<year>/<month>/<path>')
@try_except()
def wordpress_images(year, month, path):
    image_url = 'wp-content/uploads/{}/{}/{}'.format(year, month, path)

    wordpress = db.session.query(Wordpress).filter_by(type='image').filter_by(val=image_url).one()
    url_name = wordpress.redirect

    return redirect(url_name, 301)


@app.route('/blog/<url_name>/', methods=['GET'])
@try_except()
def get_post_by_name(url_name):
    p = db.session.query(Post).filter_by(url_name=url_name).one()
    return post(p.id)


@app.route('/', methods=['GET'])
@app.route('/home/', methods=['GET'])
@app.route('/post/', methods=['GET'])
@try_except()
def home():
    '''
    Grab all published posts and display for user along with category
    '''

    posts = db.session.query(Post, Category).join(Category) \
        .filter(Post.is_published == True) \
        .order_by(Post.creation_date.desc())  \
        .all()

    project_intro_posts = db.session.query(ProjectPost).filter_by(order_no=0)
    project_intro_post_ids = [p.post_id for p in project_intro_posts]

    posts = [
        {
            'title': p.title,
            'post_id': p.id,
            'url_name': p.url_name,
            'category': category.name,
            'category_url_name': category.url_name,
            'category_id': category.id,
            'is_project': True if p.id in project_intro_post_ids else False,

        }
        for p, category in posts
    ]
    return render_template('home.html', posts=posts)


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
            'category': c.name,
            'post_id': p.id,
            'is_published': p.is_published,
            'url_name': p.url_name,
            'category_id': c.id
        }
        for p, c in posts
    ]

    return render_template('admin-post.html', posts=posts)


def print_tree(tree, depth=0):
    for child in tree:
        print('    ' * depth + child['category'].name)
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


@app.route('/blog/category/', methods=['GET'])
@try_except()
def category():
    '''
    Returns a list of categories and the associated post count within each
    '''
    # TODO I want /projects/ to resuse this and only return a subset of categories who are project categories
    categories = db.session.query(Category, func.count(1)) \
        .select_from(Post).outerjoin(CategoryPost).outerjoin(Category) \
        .filter(Post.is_published == True) \
        .group_by(Category) \
        .order_by(Category.parent_id)

    title = 'Blog Categories'

    tree = []
    for category, count in categories:
        if category is not None:
            add_node(category, tree)
            category.count = count

    print_tree(tree)

    project_categories = db.session.query(Project).all()
    project_category_ids = [project_category.category_id for project_category in project_categories]

    for depth, cat in iter_tree(tree):
        print(cat)

    categories = [
        {
            'depth': depth,
            'name': category.name,
            'category_id': category.id,
            'url_name': category.url_name,
            'count': category.count,
            'is_project': True if category.id in project_category_ids else False,
        }
        for depth, category in iter_tree(tree)
    ]

    # Move uncategorized which has a low id to the back so it's not so prominent in the UI
    uncategorized_id = get_uncategorized_id()
    uncategorized_id = next((i for i, cat in enumerate(categories) if cat['category_id'] == uncategorized_id), None)
    if uncategorized_id is not None:
        uncategorized = categories.pop(uncategorized_id)
        categories.append(uncategorized)

    app.logger.debug("categories is")
    app.logger.debug(categories)

    return render_template('category.html', categories=categories, title=title)


def _get_project_category():
    return db.session.query(Category).filter_by(name="Projects").one()


@app.route("/projects/", methods=['GET'])
@try_except()
def get_projects():
    """
    This needs to be changed to the following:
    It should return the /category/ page, except contain only categories who are Project categories
    """
    categories = db.session.query(Category, func.count(1)) \
        .select_from(Post).outerjoin(CategoryPost).outerjoin(Category).join(Project) \
        .filter(Post.is_published == True) \
        .group_by(Category) \
        .order_by(Category.parent_id)

    title = 'Projects'

    categories = [
        {
            'depth': 0,
            'name': category.name,
            'category_id': category.id,
            'url_name': category.url_name,
            'count': count,
            'is_project': True,
        }
        for category, count in categories
    ]

    app.logger.debug("categories is")
    app.logger.debug(categories)

    return render_template('category.html', categories=categories, title=title)


@app.route('/projects/<url_name>/', methods=['GET'])
@try_except()
def get_project_post(url_name):
    """
    A Project has many posts, but only one introduction post.
    The /projects/url_name/ route should return the introduction post for a project.

    We know a post belongs to a project if it is in ProjectPost
    We know if a post is an introduction post to a project if its order_no is 0
    """
    p = db.session.query(Post)\
        .join(ProjectPost) \
        .filter(Post.url_name == url_name) \
        .filter(ProjectPost.order_no == 0) \
        .one()

    # TODO why not post(post.id) ?
    return post(p.id)


@app.route('/resume/', methods=['GET'])
@try_except()
def resume():
    return get_post_by_name('resume')


@app.route('/api/search/post/', methods=['GET'])
@try_except(api=True)
def search_posts():
    app.logger.debug(request.url)
    if not request.args:
        return jsonify({"error": "provide query params"}), 400
    app.logger.debug(request.args)

    if 'category_id' not in request.args and 'search' not in request.args:
        return jsonify({"error": "unknown query params {}".format(request.args)}), 400

    if 'category_id' in request.args:
        posts = db.session.query(Post).join(CategoryPost) \
            .filter(CategoryPost.category_id == request.args['category_id']) \
            .filter(Post.is_published == True) \
            .order_by(desc(Post.creation_date))

    if 'search' in request.args:
        searches = request.args['search'].lower().split()
        app.logger.debug(searches)

        q = db.session.query(Post)

        q = q.filter(or_(func.lower(Post.title).like('%' + search + '%') for search in searches))
        posts = q

    posts = [
            {
                'title': post.title,
                'url_name': post.url_name
            }
            for post in posts.all()
        ]

    return jsonify(data=posts), 200


@app.route('/blog/category/<url_name>/', methods=['GET'])
@try_except()
def category_posts_by_name(url_name):
    category = db.session.query(Category).filter_by(url_name=url_name).one()
    category_id = category.id
    category_name = category.name
    category_url_name = category.url_name
    category_description = category.description

    posts = db.session.query(Post).join(CategoryPost) \
        .filter(CategoryPost.category_id == category_id) \
        .filter(Post.is_published == True) \
        .order_by(desc(Post.creation_date)) \
        .all()

    project_introduction_posts = db.session.query(ProjectPost).filter_by(order_no=0)

    def make_url(post):
        if post.url_name == 'resume':
            return '/resume/'
        if post.id in project_introduction_posts:
            # Only project introduction posts get /projects/ url, every other post gets the normal /blog/
            # Unless we wanted the other posts to get /projects/<url_name>/ post ...
            # If we wanted that, I would need to add the few posts for the python blog to the wordpress url resolution..
            return '/projects/{}/'.format(post.url_name)
        return '/blog/{}/'.format(post.url_name)

    posts = [
        {
            'title': p.title,
            'post_id': p.id,
            'url': make_url(p),
        }
        for p in posts
    ]

    return render_template('category-posts.html', posts=posts, title=category_name, category_name=category_name, category_id=category_id,
                           category_url_name=category_url_name, category_description=category_description)


@app.route('/admin/', methods=['GET'])
@try_except()
def admin():
    if 'logged_in' not in session or not session['logged_in']:
        return redirect(url_for('admin_login'))

    return render_template('admin.html')


@app.route('/admin/create/', methods=['GET', 'POST'])
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

    user = User(first_name=first_name, last_name=last_name, email=email, password=password, is_admin=True)
    db.session.add(user)
    db.session.flush()

    # Create temporary Resume post
    uncategorized_description = "Matthew Moisen's uncategorized blog posts"
    uncategorized = Category(name='Uncategorized', url_name='uncategorized',
                             description=uncategorized_description)

    # TODO Improve this description
    projects_description = "Matthew Moisen's projects"
    projects = Category(name='Projects', url_name='projects',
                        description=projects_description)
    db.session.add(uncategorized)
    db.session.add(projects)
    db.session.flush()

    post = Post(user_id=user.id, title="Résumé", url_name='resume', description='Résumé for Matthew Moisen',
                content='My Résumé', is_published=True,
                is_commenting_disabled=True, category_id=uncategorized.id)
    db.session.add(post)
    db.session.flush()

    category_post = CategoryPost(category_id=uncategorized.id, post_id=post.id)
    db.session.add(category_post)

    db.session.commit()

    return redirect(url_for('admin_login'))


@app.route('/admin/logout/', methods=['GET'])
def admin_logout():
    session.clear()
    return redirect(url_for('home'))


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
            app.logger.warn("Failed log in attempt with email {}".format(email))
            resubmit = True
        else:
            resubmit = not sha256_crypt.verify(password, user.password)
            app.logger.debug("Verify was {}".format(resubmit))
            if resubmit:
                app.logger.warn("Failed log in attempt with email {}".format(email))

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
            'url_name': category.url_name,
            'description': category.description,
            'depth': depth
        }
        for depth, category in iter_tree(tree)
    ]


def make_project_category(category):
    """
    if parent_id is not None:
    print "its not none!"
    projects_category_id = _get_project_category().id
    if parent_id == projects_category_id:
    """
    print("parent id is project category!")
    try:
        project = db.session.query(Project).filter_by(category_id=category.id).one()
    except NoResultFound:
        print("no project found, adding it now")
        # This is a brand new project category, no updates. Add to project table
        project = Project(category_id=category.id)
        db.session.add(project)
    else:
        # This category is already a project and we are updating.
        print("we found a project oh no")
        try:
            # Search for the introduction to make updates
            project_post = db.session.query(Post).join(ProjectPost) \
                .filter(ProjectPost.order_no == 0) \
                .filter(ProjectPost.project_id == project.id) \
                .one()
        except NoResultFound:
            print("we found a project post")
            # User is modifying the category/project before he added any posts
            pass
        else:
            # Make sure introduction post has the same details as the category
            if project_post.title != category.name or project_post.url_name != category.url_name or project_post.description != category.description:
                project_post.title = category.name
                project_post.url_name = category.url_name
                project_post.description = category.description
                db.session.add(project_post)


@app.route('/admin/category/', methods=['GET', 'POST'])
@app.route('/admin/category/<int:category_id>/', methods=['GET', 'POST'])
@try_except()
@login_required
def admin_category_create(category_id=None):
    name = session.pop('category_url_name', '')
    parent_id = session.get('category_parent_id', None)
    url_name = session.pop('category_url_name', '')
    description = session.pop('category_description', '')

    categories = get_categories()

    if request.method == 'GET':
        if category_id is not None:
            # This is for updates
            category = db.session.query(Category).filter_by(id=category_id).one()
            name = category.name
            parent_id = category.parent_id
            url_name = category.url_name
            description = category.description

        return render_template('admin-category-create.html',
                               name=name,
                               description=description,
                               url_name=url_name,
                               category_id=category_id,
                               categories=categories,
                               parent_id=parent_id)

    elif request.method == 'POST':
        category_id = request.form['category_id']
        name = request.form['category_name']
        parent_id = request.form['category_parent_id']
        url_name = request.form['category_url_name']
        description = request.form['category_description']
        try:
            parent_id = int(parent_id)
        except ValueError:
            parent_id = None

        try:
            category_id = int(category_id)
        except ValueError:
            category_id = None

        if category_id is None:
            category = Category()
        else:
            category = db.session.query(Category).filter_by(id=category_id).one()

        category.name = name
        category.parent_id = parent_id

        if url_name == '':
            url_name = re.sub(r'[/:\\.;,?\{}\[\]|]', '', name)
            url_name = ' '.join(url_name.split())
            url_name = url_name.lower().replace(' ', '-')

        if description == '':
            description = "Matthew Moisen's commentary on {}".format(category.name)

        category.url_name = url_name
        category.description = description

        db.session.add(category)
        resubmit = False

        try:
            db.session.flush()
        except IntegrityError as ex:
            flash(str(ex), 'error')
            resubmit = True

        # Check if category is a project and handle the category/project logic
        if not resubmit and parent_id is not None:
            print("its not none!")
            projects_category_id = _get_project_category().id
            if parent_id == projects_category_id:
                print("parent id is project category!")
                make_project_category(category)

        app.logger.debug("ABOUT TO COMMIT")
        if not resubmit:
            try:
                db.session.commit()
            except IntegrityError as ex:
                flash(str(ex), 'error')
                resubmit = True

        if resubmit:
            db.session.rollback()
            session['category_url_name'] = url_name
            session['category_description'] = description
            session['category_name'] = name
            session['category_parent_id'] = parent_id
            return redirect(url_for('admin_category_create'))

        flash("Category '{}' created successfully".format(name), 'success')
        ping_google_sitemap()

        # This makes it easy to rapidly create multiple categories under the same parent by setting the UI's
        # parent_id column to either this category id or a parents
        if parent_id is None:
            session['category_parent_id'] = category.id
        else:
            session['category_parent_id'] = parent_id

        return redirect(url_for('admin_category_create'))


@app.route('/api/upload-image-png/', methods=['POST'])
@try_except(api=True)
@login_required
@csrf(request_type='json')
def upload_image2():
    data = request.json['data']
    file_name = request.json['file_name']

    file_name = secure_filename(file_name)

    file_path = os.path.join(app.config['UPLOAD_FOLDER'], file_name)

    if os.path.isfile(file_path):
        raise UserError("A file with that name has already been saved")

    data = data.split('data:image/png;base64,')[1]

    image = Image.open(io.BytesIO(base64.b64decode(data)))

    image.save(file_path, 'PNG')

    markdown = '\n\n' + '![{file_name}](/static/images/{file_name}) \n'.format(file_name=file_name)

    # http://stackoverflow.com/a/6966225/1391717

    print(data)

    return jsonify({"markdown": markdown})


@app.route('/api/upload-image/', methods=['POST'])
@try_except(api=True)
@login_required
@csrf(request_type='json')
def upload_image():
    if not request.files:
        raise UserError("File is empty")

    file = request.files['file']

    if file.filename is None or file.filename == '':
        raise UserError("Filename is none or empty")

    file_name = secure_filename(file.filename)

    file_path = os.path.join(app.config['UPLOAD_FOLDER'], file_name)

    if os.path.isfile(file_path):
        raise UserError("A file with that name has already been saved")

    try:
        file.save(file_path)
    except IOError as ex:
        raise ServerError("Could not save file: {}".format(ex))

    markdown = '\n\n' + '![{file_name}](/static/images/{file_name}) \n'.format(file_name=file_name)

    return jsonify({"markdown": markdown}), 200


def draft_logic(post_id, draft_id, submit):
    """
    draft_id will always not be None, unless its a new post, user never paused for 5 seconds and then published.

    We are now publishing a post and so we need to deal with the drafts.
    If the post was a brand new post, we can simply delete the post whose id == draft id, and delete it from draft
        table.
    If we are saving a draft of a new post that was never saved, post_id is not None. Logic is the same as above:
        delete the post whose id == draft id, and delete it from draft
        Draft table will have a null original_post_id
    If we are saving a draft of an old post that was never saved, post_id is not None.
        For this we should set this draft post as the true post, and set the original old post as a draft ?
        Draft table will not have a null original_post_id
    If we are saving an old post, who has a draft, post_id is not None
        Save this old post, dont touch the drafts

    """
    if post_id == '':
        post = Post()
        app.logger.debug("This is a brand new post")
        # This is a brand new post. Just delete the draft
        if draft_id:
            # Delete saved draft if the post was never saved for real before
            if draft_id != post_id:
                db.session.query(Post).filter_by(id=draft_id).delete()
    else:
        post = db.session.query(Post).filter_by(id=post_id).one()
        # This is either saving a draft of a new post,
        # saving a draft of an old post,
        # or saving an old post, who may or may not have drafts
        #
        # 1 saving a draft of a new post that was never saved
        try:
            draft = db.session.query(Draft).filter_by(draft_post_id=post_id).one()
        except NoResultFound:
            app.logger.debug("We are saving an old post, not any draft")
            drafts = db.session.query(Draft).filter_by(original_post_id=post_id).all()
            if drafts:
                app.logger.debug("This old past has some drafts, lets delete them")
                # We are saving an old post, who has many drafts, dont do anything
                # DELETE ALL DRAFTS
                app.logger.debug("We have old drafts, deleting now")
                db.session.query(Post).filter(Post.id.in_([d.draft_post_id for d in drafts])).delete(synchronize_session=False)
                db.session.query(Draft).filter_by(original_post_id=post_id).delete()
        else:
            # We are saving a draft of some post
            if draft.original_post_id:
                app.logger.debug("We are saving a draft of an old post who was saved")
                # We are saving a draft of some old post. Old post should become the draft
                # If user wants to publish this draft, set old post to unpublished
                # We also have to change the old posts url-name and title so uniqueness remains
                if submit == 'publish':
                    u = str(uuid.uuid4())
                    db.session.query(Post).filter_by(id=draft.original_post_id).update(
                        {
                            'is_published': False,
                            'title': Post.title + u,
                            'url_name': Post.url_name + u,
                        }, synchronize_session=False
                    )
                    temp = draft.draft_post_id
                    draft.draft_post_id = draft.original_post_id
                    draft.original_post_id = temp

            else:
                # we are saving a draft of a new post who was never saved
                # Just delete the old draft
                app.logger.debug("We are saving a draft of a new post who was never saved")
                db.session.query(Draft).filter_by(draft_post_id=post_id).delete()

    return post


@app.route('/admin/post/new/', methods=['GET', 'POST'])
@app.route('/admin/post/<int:post_id>/', methods=['GET', 'POST'])
@try_except()
@login_required
def admin_post_create(post_id=None):
    def admin_post_create_error(message, title, content, main_category_id, other_category_ids, post_id,
                                is_commenting_disabled, draft_id):
        flash(message, 'error')
        session['title'] = title
        session['content'] = content
        session['main_category_id'] = main_category_id
        session['other_category_ids'] = other_category_ids
        session['post_id'] = post_id
        session['is_commenting_disabled'] = is_commenting_disabled
        session['draft_id'] = draft_id

    title = session.pop('title', '')
    content = session.pop('content', '')
    m = markdown.markdown(content)
    main_category_id = session.pop('main_category_id', '')
    other_category_ids = session.pop('other_category_ids', [])
    url_name = session.pop('url_name', '')
    description = session.pop('url_name', '')
    post_id = '' if post_id is None else post_id
    is_commenting_disabled = session.pop('is_commenting_disabled', False)
    draft_id = session.pop('draft_id', '')
    categories = get_categories()

    # This is other drafts of an original post; user should be notified of them
    drafts = []

    if request.method == 'GET':

        if post_id != '':
            # Edit
            post = db.session.query(Post).filter_by(id=post_id).one()
            title = post.title
            content = post.content
            m = markdown.markdown(content)
            url_name = post.url_name
            description = post.description
            post_id = post.id
            main_category_id = post.category_id
            is_commenting_disabled = post.is_commenting_disabled
            # Are we editing a post for the first time, or are we opening a draft of a new post, or a draft of an old post?
            # Need to find if this post is a draft, or has a draft
            # If we are opening a draft, set draft_id to post_id
            # We DO NOT make drafts of drafts. We always edit a draft
            # We can however make N drafts of a old post, I suppose
            try:
                db.session.query(Draft).filter_by(draft_post_id=post.id).one()
            except NoResultFound:
                # I am not a draft
                draft_id = ''
            else:
                # I am a draft
                draft_id = post_id

            drafts = db.session.query(Draft).filter_by(original_post_id=post.id).all()
            if drafts:
                # I am original post, but there are saved drafts that user can look at if he wants
                # Notify user of other drafts
                drafts = [
                    {
                        'post_id': d.draft_post_id
                    }
                    for d in drafts
                ]

            other_categories = db.session.query(CategoryPost).filter_by(post_id=post_id).all()
            other_category_ids = [other_category.category_id for other_category in other_categories]
        else:
            # New post
            draft_id = ''
            main_category_id = get_uncategorized_id()

        return render_template('admin-post-create.html',
                               title=title,
                               content=content,
                               markdown=m,
                               post_id=post_id,
                               draft_id=draft_id,
                               drafts=drafts,
                               description=description,
                               url_name=url_name,
                               categories=categories,
                               main_category_id=main_category_id,
                               other_category_ids=other_category_ids,
                               is_commenting_disabled=is_commenting_disabled)

    elif request.method == 'POST':
        app.logger.debug("Form is ")
        app.logger.debug(request.form)
        post_id = request.form['post_id']
        draft_id = request.form['draft_id']
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

        # Category can be null for an uncategorized post
        # not any more ...
        uncategorized_id = get_uncategorized_id()
        main_category_id = int(main_category_id)

        other_category_ids = list(map(int, other_category_ids))

        # If user forgot to select a main category id, pick the first one from other categories
        if other_category_ids and main_category_id == uncategorized_id:
            main_category_id = other_category_ids[0]

        # Make sure to add main_category_id if it wasn't selected in other_category_ids
        #if not other_category_ids and main_category_id is not None:
        if main_category_id != uncategorized_id and main_category_id not in other_category_ids:
            other_category_ids.append(main_category_id)

        dt = datetime.utcnow()

        post = draft_logic(post_id, draft_id, submit)

        post.user_id = session['user_id']
        post.is_commenting_disabled = is_commenting_disabled

        post.title = title
        # What if I want to legitimately use '\r\n' ?
        post.content = content.replace('\r\n', '\n')

        if url_name == '':
            url_name = re.sub(r'[/:\\.;,?\{}\[\]|]', '', title)
            url_name = ' '.join(url_name.split())
            url_name = url_name.lower().replace(' ', '-')

        if description == '':
            description = title.capitalize()

        post.description = description

        post.url_name = url_name

        # If main category is under the Projects category, auto create a new subcategory of Projects
        # using this post name and url and description
        # And set this post's category to the new subcategory
        project_category_id = _get_project_category().id
        if main_category_id == project_category_id:
            subcategory = Category(name=post.title, url_name=post.url_name, description=post.description,
                                   parent_id=project_category_id)
            db.session.add(subcategory)
            db.session.flush()
            make_project_category(subcategory)
            main_category_id = subcategory.id
            other_category_ids.append(main_category_id)

        post.category_id = main_category_id

        if title == '' or content == '':
            admin_post_create_error('Title or content is empty', title, content, main_category_id, other_category_ids,
                                    post_id, is_commenting_disabled, draft_id)
            return redirect(url_for('admin_post_create'))

        if submit == 'publish':
            post.is_published = True
        elif submit == 'draft':
            post.is_published = False

        db.session.add(post)

        try:
            db.session.flush()

        except SQLAlchemyError as ex:
            db.session.rollback()
            app.logger.exception("Error saving post {}".format(ex))
            admin_post_create_error(str(ex), title, content, main_category_id, other_category_ids,
                                    post_id, is_commenting_disabled, draft_id)
            return redirect(url_for('admin_post_create'))

        # Associate this post with all of its categories
        # Its easier to just delete all the M:N and start over
        db.session.query(CategoryPost).filter_by(post_id=post.id).delete()

        # other_category_ids has all the other_category_ids AND the main_category_id in it now
        all_category_ids = set(other_category_ids)
        back = {}
        get_category_tree(back)
        other_categories = []
        if other_category_ids:
            other_categories = db.session.query(Category).filter(Category.id.in_(other_category_ids)).all()
        for other_category in other_categories:
            for ascendant in find_ascendants(back, other_category):
                all_category_ids.add(ascendant.id)

        category_posts = [CategoryPost(category_id=category_id, post_id=post.id) for category_id in all_category_ids]
        if category_posts:
            db.session.bulk_save_objects(category_posts, return_defaults=True)

        # Now update last_modified_time for all categories associated with this post to reflect on the site-map.xml
        if all_category_ids:
            db.session.query(Category).filter(Category.id.in_(all_category_ids)).update({'last_modified_date': dt}, synchronize_session=False)

        # Associate this post with its project
        try:
            project = db.session.query(Project).filter_by(category_id=main_category_id).one()
        except NoResultFound:
            # This post doesn't belong to a project category
            pass
        else:
            # Check to see if this is the first post in this project
            project_posts = db.session.query(ProjectPost).filter_by(project_id=project.id)\
                .order_by(ProjectPost.order_no) \
                .all()

            is_intro_post = False
            is_new = False
            order_no = 0
            if not project_posts:
                is_intro_post = True
                is_new = True
                order_no = 0
            else:
                project_post = next((pp for pp in project_posts if pp.post_id == post.id), False)
                if project_post:
                    if project_post.order_no == 0:
                        is_intro_post = True
                else:
                    is_new = True
                    # Assume that order should be the last for now.
                    order_no = project_posts[-1].order_no + 1

            if is_new:
                project_post = ProjectPost(project_id=project.id, post_id=post.id, order_no=order_no)
                db.session.add(project_post)

            if is_intro_post:
                # The introduction post must have the same Title, url, and description as the project category
                project_category = db.session.query(Category).filter_by(id=project.category_id).one()
                if post.title != project_category.name or post.url_name != project_category.url_name or post.description != project_category.description:
                    post.title = project_category.name
                    post.url_name = project_category.url_name
                    post.description = project_category.description
                    # I don't think this is necessary since it was already added
                    db.session.add(post)

        try:
            db.session.commit()
        except SQLAlchemyError as ex:
            db.session.rollback()
            app.logger.exception("Error saving Post {}".format(ex))
            admin_post_create_error(str(ex), title, content, main_category_id, other_category_ids,
                                    post_id, is_commenting_disabled, draft_id)
            return redirect(url_for('admin_post_create'))

        ping_google_sitemap()

        return redirect(url_for('post', post_id=post.id))


@app.route('/admin/post/<int:post_id>/publish/', methods=['GET'])
@try_except()
@login_required
def mark_post_as_published(post_id):
    last_url = request.args.get('last_url', 'post')

    post = db.session.query(Post).filter_by(id=post_id).one()
    if not post.is_published:
        post.is_published = True
        db.session.add(post)
        db.session.commit()

    ping_google_sitemap()

    return redirect(url_for(last_url, post_id=post_id))


@app.route('/admin/post/<int:post_id>/draft/', methods=['GET'])
@try_except()
@login_required
def mark_post_as_draft(post_id):
    post = db.session.query(Post).filter_by(id=post_id).one()

    last_url = request.args.get('last_url', 'post')

    if post.is_published:
        post.is_published = False
        db.session.add(post)
        db.session.commit()

    ping_google_sitemap()

    return redirect(url_for(last_url, post_id=post_id))


@app.route('/admin/post/<int:post_id>/delete/', methods=['GET'])
@try_except()
@login_required
def mark_post_as_deleted(post_id):
    post = db.session.query(Post).filter_by(id=post_id).one()
    db.session.delete(post)
    db.session.commit()

    ping_google_sitemap()

    return redirect(url_for('home'))


def text_to_number(val):
    try:
        return int(val)
    except ValueError:
        return None


def uuid_if_empty(val):
    if val == '':
        return str(uuid.uuid4())
    return val


@app.route('/api/save-draft/', methods=['POST'])
@try_except(api=True)
@login_required
@csrf(request_type='json')
def save_draft():
    data = request.json
    app.logger.debug("data is {}".format(data))

    content = data['content']
    title = data['title']
    url_name = data['url_name']

    description = data['description']
    post_id = text_to_number(data['post_id'])
    main_category_id = text_to_number(data['main_category_id'])
    draft_id = text_to_number(data['draft_id'])

    # I don't think main_category_id will ever be None as it defaults to uncategorized right
    if main_category_id is None:
        main_category_id = get_uncategorized_id()

    if title != '':
        if url_name == '':
            url_name = re.sub(r'[/:\\.;,?\{}\[\]|]', '', title)
            url_name = ' '.join(url_name.split())
            url_name = url_name.lower().replace(' ', '-')

            if description == '':
                description = title.capitalize()
    else:
        title = str(uuid.uuid4())
        if url_name == '':
            url_name = title
        if description == '':
            description = url_name

    if description == '':
        description = title
    """
        draft_id is None under the following condition:
        * User created new post/edit old post, and this is the very first time this api has been called
            We need to create a draft and save it.

        draft_id is not None under the following conditions (OR):
        * User created new post/edit old post, and this is the 2nd through Nth time this api has been called
        * User opens a draft. draft_id == post_id - dont make a new draft
        *
    """
    if draft_id is None:
        user_id = session['user_id']
        post = Post(user_id=user_id)
    else:
        post = db.session.query(Post).filter_by(id=draft_id).one()

    post.content = content
    post.description = description
    post.category_id = main_category_id
    post.title = title
    post.url_name = url_name
    post.is_published=False

    db.session.add(post)
    try:
        db.session.flush()
    except IntegrityError as ex:
        db.session.rollback()
        app.logger.debug("Caught in flush {}".format(ex))
        u = str(uuid.uuid4())
        title += u
        url_name += u
        post.title = title
        post.url_name = url_name
        app.logger.debug(post.title)
        app.logger.debug(post.url_name)
        app.logger.debug(post.description)
        db.session.add(post)
        db.session.flush()

    if draft_id is None:
        draft = Draft(original_post_id=post_id, draft_post_id=post.id)
        db.session.add(draft)

    db.session.commit()

    draft_id = post.id

    db.session.commit()

    ret = {
        'draft_id': draft_id,
    }

    return jsonify(ret), 200


@app.route('/api/preview-post/', methods=['POST'])
@try_except(api=True)
def preview_post():
    data = request.json
    app.logger.debug("data is {}".format(data))

    content = markdown.markdown(data['content'])

    return jsonify({"content": content}), 200


def get_project_table_of_contents(post):
    posts = db.session.query(Post, ProjectPost).join(ProjectPost).join(Project) \
        .filter(Project.category_id == post.category_id) \
        .order_by(ProjectPost.order_no)

    def make_url(post, project_post):
        if project_post.order_no == 0:
            return '/projects/{}/'.format(post.url_name)
        return '/blog/{}/'.format(post.url_name)

    return [
        {
            'post_id': p.id,
            'order_no': project_post.order_no,
            'title': p.title,
            'url': make_url(p, project_post),
            'is_published': p.is_published,
            'this_post_id': post.id
        }
        for p, project_post, in posts
    ]


@app.route('/post/<int:post_id>/', methods=['GET'])
@try_except()
def post(post_id):
    post = db.session.query(Post).filter_by(id=post_id).one()

    is_admin = check_admin_status()

    # Only admin should be able to view drafts
    if not post.is_published:
        if not is_admin:
            abort(404)

    category_id = post.category_id

    title = post.title
    # markdown should be applied when comment is created
    content = markdown.markdown(post.content)
    post_id = post.id
    is_published = post.is_published
    url_name = post.url_name
    description = post.description
    is_commenting_disabled = post.is_commenting_disabled

    # Because all posts actually route through this function, the canonical url needs to be set appropriately
    # I think it would be better to change this into a normal function instead of a route
    canonical_url = '{}{}'.format(app.config['WEB_PROTOCOL'], app.config['DOMAIN'])
    if url_name == 'resume':
        canonical_url += 'resume/'
    else:
        # See if this post is the introduction post to a Project
        try:
            project_post = db.session.query(ProjectPost).filter_by(post_id=post_id).filter_by(order_no=0).one()
        except NoResultFound:
            canonical_url += 'blog/{}/'.format(url_name)
        else:
            canonical_url += 'projects/{}/'.format(url_name)
            # No need to find category's description/url_name/etc as its enforced to be identical on post creation

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

    table_of_contents = get_project_table_of_contents(post)

    return render_template('post.html',
                           canonical_url=canonical_url,
                           title=title,
                           content=content,
                           post_id=post_id,
                           url_name=url_name,
                           is_published=is_published,
                           description=description,
                           table_of_contents=table_of_contents,
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

# Does this need to change to /blog/<post_url_name>/comment/ ?
# Should /comment/ be removed?? ya..
@app.route('/blog/<url_name>/', methods=['POST'])
@try_except()
def post_comment(url_name):
    post = db.session.query(Post).filter_by(url_name=url_name).one()
    post_id = post.id

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

    creation_date = datetime.utcnow()

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

    ping_google_sitemap()

    return redirect(url_for('admin_comment_queue'))


@app.route('/admin/comment/<int:comment_id>/delete/')
@try_except()
@login_required
def admin_comment_delete(comment_id):
    comment = db.session.query(Comment).filter_by(id=comment_id).one()
    db.session.delete(comment)
    db.session.commit()

    return redirect(url_for('admin_comment_queue'))


@app.route('/admin/log/', methods=['GET'])
@try_except()
@login_required
def admin_log():
    logs = db.session.query(Log).order_by(Log.creation_date.desc())

    logs = [
        {
            'id': log.id,
            'logger': log.logger,
            'level': log.level,
            'trace': log.trace,
            'message': log.message,
            'path': log.path,
            'method': log.method,
            'ip': log.ip,
            'is_admin': log.is_admin,
            'creation_date': log.creation_date
        }
        for log in logs
    ]

    return render_template('admin-log.html', logs=logs)


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


def math_spam():
    number = list(number_words.keys())[random.randrange(1, len(number_words) + 1) - 1]
    number_to_word = list(number_words.keys())[random.randrange(1, len(number_words) + 1) - 1]
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
        app.logger.warn("User entered a string or empty in spam check")
        flash("Enter a number, not a string, in humanity check", 'error')
        resubmit = True

    if not resubmit and 'spam_check' not in session:
        app.logger.warn("spam_check was not in session")
        flash("Please try humanity check again", 'error')
        resubmit = True

    original_spam_check = session.pop('spam_check')
    if not resubmit and not original_spam_check == input_spam_check:
        app.logger.warn("Spam check failed")
        flash("Please try humanity check again", 'error')
        resubmit = True

    return resubmit


site_map_url_template = '''<url>
<loc>{url}</loc>
<lastmod>{last_modified_time}</lastmod>
<changefreq>{change_frequency}</changefreq>
<priority>{priority}</priority>
</url>
'''


def ping_google_sitemap():
    if not app.config['ENABLE_GOOGLE_SITEMAP_PING']:
        app.logger.warn("Pinging google site map isn't activated")
        return
    if app.config['WEB_PROTOCOL'] == 'http://':
        app.logger.error("Google sitemap ping is on, but web protocol is http instead of https")
        return
    if 'localhost' in app.config['DOMAIN'] or '0.0.0.0' in app.config['DOMAIN']:
        app.logger.error("Google sitemap ping is on, but domain is localhost")

    url = 'https://www.google.com/ping?sitemap={}{}sitemap.xml'.format(
        app.config['WEB_PROTOCOL'], app.config['DOMAIN']
    )
    try:
        r = requests.get(url)
    except requests.RequestException as ex:
        app.logger.exception("Couldn't ping google about site map: {}, url used was {}".format(ex, url))
    else:
        if r.status_code != 200:
            app.logger.error("Failed to ping google sitemap:\n{}\n\nurl was {}".format(r.text, url))


def make_url(url, last_modified_time, change_frequency='weekly', priority='0.5'):
    return site_map_url_template.format(
        url=url, last_modified_time=last_modified_time, change_frequency=change_frequency, priority=priority
    )


@app.route('/sitemap.xml', methods=['GET'])
def sitemap():
    template = '''<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
{urls}
</urlset>
'''

    urls = []
    DATE_FORMAT = '%Y-%m-%d'

    no_max = datetime.utcnow().strftime(DATE_FORMAT)

    single_pages = [
        ('home', db.session.query(func.max(Post.last_modified_date)).select_from(Post), '', '1.0'),
        ('category', db.session.query(func.max(Category.last_modified_date)).select_from(Category), 'blog/category/', '0.5'),
        ('projects', db.session.query(func.max(Post.last_modified_date)).select_from(Post).join(Category) \
            .filter(Category.name == 'Projects'), 'projects/', '0.5'),
        ('resume', db.session.query(func.max(Post.last_modified_date)).select_from(Post) \
            .filter(Post.url_name == 'resume'), 'resume/', '0.5')
    ]

    for name, q, url_postfix, priority in single_pages:
        try:
            max = q.one()[0]
        except SQLAlchemyError as ex:
            app.logger.exception("Failed to create sitemap url for {}! {}".format(name, ex))
        else:
            if max:
                max = str(max.strftime(DATE_FORMAT))
            else:
                max = no_max
            urls.append(make_url('{}{}{}'.format(app.config['WEB_PROTOCOL'], app.config['DOMAIN'], url_postfix), last_modified_time=max,
                                 priority=priority))

    project_posts = db.session.query(ProjectPost).filter_by(order_no=0).all()
    project_post_ids = [p.post_id for p in project_posts]

    # Now do posts
    for url_name, last_modified_date, post_id in db.session.query(Post.url_name, Post.last_modified_date, Post.id) \
            .filter(Post.is_published == True):
        if url_name != 'resume':
            # Prevent resume from given a url of /blog/resume and use the /resume/ instead
            url_postfix = str(url_name)
            last_modified_time = str(last_modified_date.strftime(DATE_FORMAT))
            u = '{}{}blog/{}/'
            if post_id in project_post_ids:
                u = '{}{}projects/{}/'
            urls.append(make_url(u.format(app.config['WEB_PROTOCOL'], app.config['DOMAIN'], url_postfix),
                                 last_modified_time=last_modified_time, priority='0.5'))

    # Now to categories
    for url_name, last_modified_date in db.session.query(Category.url_name, Category.last_modified_date):
        if url_name != 'projects':
            # Prevent projects from given a url of /blog/category/projects and use the /projects/ instead
            url_postfix = str(url_name)
            last_modified_time = str(last_modified_date.strftime(DATE_FORMAT))
            urls.append(make_url('{}{}blog/category/{}/'.format(app.config['WEB_PROTOCOL'], app.config['DOMAIN'], url_postfix),
                                 last_modified_time=last_modified_time, priority='0.5'))

    xml = template.format(urls=''.join(urls))
    print(xml)
    try:
        ElementTree.fromstring(str(xml))
    except ElementTree.ParseError:
        app.logger.critical("Sitemap XML IS INVALID!!!")
        # TODO Should probably email myself

    return template.format(urls=''.join(urls))

