import unittest
import os
from sqlalchemy.engine import Engine
from sqlalchemy import event
from blog import app, db
from blog.models import *
from blog.views.home import draft_logic, get_uncategorized_id
from flask import request, session, template_rendered
import json
from passlib.hash import sha256_crypt
from sqlalchemy.exc import SQLAlchemyError, IntegrityError
from sqlalchemy.orm.exc import NoResultFound
import uuid
import nose
from functools import wraps

class TestBase(unittest.TestCase):
    __test__ = False

    def setUp(self):
        # Not sure why but this creates test.db in blog subdirectory
        db_path = os.path.join(os.path.split(__file__)[0], 'test.db')
        app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///{}'.format(db_path)
        app.config['TESTING'] = True
        app.config['SECRET_KEY'] = 'abc123'
        # Apparently foreign keys get turned on by __init__.py /
        #self.app = app.test_client()
        #self.session = self.app.session_transaction()
        db.create_all()

        uncategorized = Category(name='Uncategorized', description='Uncategorized', url_name='uncategorized')
        db.session.add(uncategorized)
        projects = Category(name='Projects', description='Projects', url_name='projects')
        db.session.add(projects)

        password = sha256_crypt.encrypt('password')
        user = User(first_name='Matthew', last_name='Moisen', email='matthew@hello.org', password=password, is_admin=True)
        db.session.add(user)

        db.session.commit()

        self.projects_id = projects.id
        self.uncategorized_id = uncategorized.id
        self.user_id = user.id


    def tearDown(self):
        db.session.remove()
        db.drop_all()


from flask import template_rendered
from contextlib import contextmanager
"""
@contextmanager
def captured_templates(app):
    recorded = []
    def record(sender, template, context, **extra):
        recorded.append((template, context))
    template_rendered.connect(record, app)
    try:
        yield recorded
    finally:
        template_rendered.disconnect(record, app)
"""
@contextmanager
def get_context_variables(app):
    recorded = []
    def record(sender, template, context, **extra):
        recorded.append(context)
    template_rendered.connect(record, app)
    try:
        yield iter(recorded)
    finally:
        template_rendered.disconnect(record, app)

def admin_login(func):
    """
    This decorator logs into the admin and sets the test_client() on self as self.c

    """
    @wraps(func)
    def _admin_login(self, *args, **kwargs):
        with app.test_client() as c:
            c.get('/admin/login/')
            spam_check = session['spam_check']
            data = {
                'email': 'matthew@hello.org', 'password': 'password', 'spam_check': spam_check
            }
            r = c.post('/admin/login/', data=data, follow_redirects=True)
            self.assertTrue(session['is_admin'])
            self.c = c
            with self.c.session_transaction() as sess:
                sess['user_id'] = self.user_id
            return func(self, *args, **kwargs)
    return _admin_login

from nose import tools

@tools.istest
class Test_DraftLogic(TestBase):
    __test__ = True
    def setUp(self):
        TestBase.setUp(self)
        self.data = {
            'content': 'test',
            'title': 'test',
            'url_name': 'test',
            'description': 'test',
            'post_id': '',
            'draft_id': '',
            'main_category_id': self.uncategorized_id,
        }


    @admin_login
    def test_lol(self):
        with get_context_variables(app) as contexts:
            r = self.c.get('/admin/post/new/', follow_redirects=True)
            csrf = session['csrf_token']
            print "hai i am csrf", csrf
            context = next(contexts)
            self.assertEquals(context['post_id'], '')
            self.assertEquals(context['draft_id'], '')

    def _assert_get_admin_post_new_variables(self, post_id, draft_id):
        with get_context_variables(app) as contexts:
            u = 'new'
            if post_id != '':
                u = post_id
            elif draft_id != '':
                u = draft_id
            r = self.c.get('/admin/post/{}/'.format(u), follow_redirects=True)
            self.csrf_token = session['csrf_token']
            context = next(contexts)
            self.assertEquals(context['post_id'], post_id)
            self.assertEquals(context['draft_id'], draft_id)

    def _ajax_save_draft(self, data):
        print "session in ajax save draft is", session
        data['_csrf_token'] = self.csrf_token
        r = self.c.post('/api/save-draft/', data=json.dumps(data), content_type='application/json',
                        follow_redirects=True, base_url='http://localhost:5000/', environ_base={
                'HTTP_REFERER': 'http://localhost:5000/',
            })
        r = json.loads(r.data)
        return r['draft_id']

    def _assert_saved_draft_brand_new(self, draft_id, **kwargs):
        post = db.session.query(Post).filter_by(id=draft_id).one()
        for k, v in kwargs.iteritems():
            self.assertEquals(getattr(post, k), v)
        draft = db.session.query(Draft).filter_by(draft_post_id=draft_id).one()
        self.assertEquals(draft.original_post_id, None)

    def _assert_saved_draft_old(self, draft_id, post_id, **kwargs):
        post = db.session.query(Post).filter_by(id=draft_id).one()
        for k, v in kwargs.iteritems():
            # For old items, the name is changed to "test<uuid4>"
            # If we split on the name with the value (test), it will create an array of length 2, where 2nd item is uuid
            value = getattr(post, k)
            value = value.split(v)
            self.assertEquals(len(value), 2)
            # This will raise an error if the uuid is wrong
            uuid.UUID(value[1], version=4)
        draft = db.session.query(Draft).filter_by(draft_post_id=draft_id).one()
        self.assertEquals(draft.original_post_id, post_id)



    @admin_login
    def test_save_draft_after_crash(self):
        """
        This tests two cases:
        User opens a brand new post, a draft is saves, and browser fails before draft is saved.
            A draft needs to be created (a Post entry, and a Draft entry with null original_post_id and draft_post_id = post.post_id)
        User opens the draft of a brand new post that was never officially saved and then officially saves the draft
            post uses draft id, not new id
        :return:
        """

        # Get /admin/post/new first
        self._assert_get_admin_post_new_variables(post_id='', draft_id='')
        print "session in tests is ", session

        # Save first draft
        draft_id = self._ajax_save_draft(self.data)
        self.data['draft_id'] = draft_id
        self._assert_saved_draft_brand_new(draft_id, title='test')

        print "session before save draft again is ", session


        # Save draft again
        self.data['title'] += 'test'
        draft_id = self._ajax_save_draft(self.data)
        self._assert_saved_draft_brand_new(draft_id, title='testtest')

        # Pretend that browser has failed and user comes back
        self._assert_get_admin_post_new_variables(post_id=draft_id, draft_id=draft_id)

        # Save draft again
        self.data['title'] += 'test'
        self.data['post_id'] = str(draft_id)
        draft_id = self._ajax_save_draft(self.data)
        self._assert_saved_draft_brand_new(draft_id, title='testtesttest')

        # Officially save the draft
        self.data['post_title'] = self.data.pop('title')
        self.data['post_content'] = self.data.pop('content')
        self.data['submit'] = 'publish'
        r = self.c.post('/admin/post/new/', data=self.data)
        # Draft should be deleted
        self.assertRaises(NoResultFound, db.session.query(Draft).filter_by(draft_post_id=draft_id).one)
        # Post should retain draft_id as id
        post = db.session.query(Post).filter_by(id=draft_id).one()
        self.assertEquals(post.title, 'testtesttest')
        self.assertEquals(post.is_published, True)

    @admin_login
    def test_save_draft_without_crash(self):
        """
        This tests the following case:

        User opens a brand new post, a draft is saved, and user officially saves the post without crashing
            A draft needs to be created,
            draft is deleted
            post uses new id, not draft id
        :return:
        """

        # Get /admin/post/new first
        self._assert_get_admin_post_new_variables(post_id='', draft_id='')

        # Save first draft
        draft_id = self._ajax_save_draft(self.data)
        self.data['draft_id'] = draft_id
        self._assert_saved_draft_brand_new(draft_id, title='test')


        # Save draft again
        self.data['title'] += 'test'
        draft_id = self._ajax_save_draft(self.data)
        self._assert_saved_draft_brand_new(draft_id, title='testtest')

        # Officially save the draft
        self.data['post_title'] = self.data.pop('title')
        self.data['post_content'] = self.data.pop('content')
        self.data['submit'] = 'publish'
        r = self.c.post('/admin/post/new/', data=self.data)
        # Draft should be deleted
        self.assertRaises(NoResultFound, db.session.query(Draft).filter_by(draft_post_id=draft_id).one)
        # Post should NOT retain draft_id as id
        self.assertRaises(NoResultFound, db.session.query(Post).filter_by(id=draft_id).one)
        post = db.session.query(Post).one()
        self.assertEquals(post.title, 'testtest')
        self.assertEquals(post.is_published, True)

    @admin_login
    def test_save_draft_of_old_post_after_crash(self):
        """
        This tests the following use cases:

        User opens old post to edit, a draft is saved, and browser fails before post is officially saved

        User opens the draft of an old post that was never officially saved, and then officially saves the draft
        :return:
        """
        old_post = Post(user_id=self.user_id, title="test", url_name="test", description="test",
                        category_id=get_uncategorized_id(), content="test", is_published=True)
        db.session.add(old_post)
        db.session.commit()

        # Get /admin/post/new first
        self._assert_get_admin_post_new_variables(post_id=old_post.id, draft_id='')
        self.data['post_id'] = str(old_post.id)

        # Save first draft
        draft_id = self._ajax_save_draft(self.data)
        self.data['draft_id'] = draft_id
        self._assert_saved_draft_old(draft_id, old_post.id, title='test')


        # Save draft again
        self.data['title'] += 'test'
        draft_id = self._ajax_save_draft(self.data)
        self._assert_saved_draft_old(draft_id, old_post.id, title='testtest')

        # Pretend that browser has failed and user comes back to draft of old post
        self._assert_get_admin_post_new_variables(post_id=draft_id, draft_id=draft_id)
        self.data['post_id'] = str(draft_id)

        # Save draft again
        self.data['title'] += 'test'
        self.data['post_id'] = str(draft_id)
        draft_id = self._ajax_save_draft(self.data)
        self._assert_saved_draft_old(draft_id, old_post.id, title='testtesttest')

        # Officially save the draft
        self.data['post_title'] = self.data.pop('title')
        self.data['post_content'] = self.data.pop('content')
        self.data['submit'] = 'publish'
        r = self.c.post('/admin/post/new/', data=self.data)
        # Draft should be deleted
        self.assertRaises(NoResultFound, db.session.query(Draft).filter_by(draft_post_id=draft_id).one)
        # Old post should be draft
        db.session.query(Draft).filter_by(draft_post_id=old_post.id).one()
        # New Post should retain draft_id as id
        post = db.session.query(Post).filter_by(id=draft_id).one()
        self.assertEquals(post.title, 'testtesttest')
        self.assertEquals(post.is_published, True)
        # old post should be unpublished
        post = db.session.query(Post).filter_by(id=old_post.id).one()
        self.assertEquals(post.is_published, False)

    @admin_login
    def test_save_draft_of_old_post_without_crash(self):
        old_post = Post(user_id=self.user_id, title="test", url_name="test", description="test",
                        category_id=get_uncategorized_id(), content="test", is_published=True)
        db.session.add(old_post)
        db.session.commit()

        # Get /admin/post/new first
        self._assert_get_admin_post_new_variables(post_id=old_post.id, draft_id='')
        self.data['post_id'] = str(old_post.id)

        # Save first draft
        draft_id = self._ajax_save_draft(self.data)
        self.data['draft_id'] = draft_id
        self._assert_saved_draft_old(draft_id, old_post.id, title='test')

        # Save draft again
        self.data['title'] += 'test'
        draft_id = self._ajax_save_draft(self.data)
        self._assert_saved_draft_old(draft_id, old_post.id, title='testtest')

        # Officially save the draft
        self.data['post_title'] = self.data.pop('title')
        self.data['post_content'] = self.data.pop('content')
        self.data['submit'] = 'publish'
        r = self.c.post('/admin/post/new/', data=self.data)
        # Draft should be deleted
        self.assertRaises(NoResultFound, db.session.query(Draft).filter_by(draft_post_id=draft_id).one)
        self.assertRaises(NoResultFound, db.session.query(Post).filter_by(id=draft_id).one)
        # Old post should be draft
        # old post should be unpublished
        post = db.session.query(Post).filter_by(id=old_post.id).one()
        self.assertEquals(post.title, 'testtest')
        self.assertEquals(post.is_published, True)






if __name__ == '__main__':
    import nose
    #nose.main()
    unittest.main()