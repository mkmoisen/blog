from blog import app
from blog import db
from blog.views import date_format
from sqlalchemy.sql.sqltypes import Date, DateTime
from sqlalchemy.sql import func


class BaseModel(db.Model):
    '''
    All Models should extend the Base model so that they can implement the json method
    '''
    __abstract__ = True


'''
class SqliteSequence(db.Model):
    """The only purpose of this is so flask-migrate doesn't try to mess with sqlite sequence table"""
    name = db.Column(db.String, primary_key=True)
    seq = db.Column(db.Integer)
    __tablename__ = 'sqlite_sequence'
    __abstract__ = True
'''

class DBSession(db.Model):
    sid = db.Column(db.String(50), primary_key=True)
    data = db.Column(db.Text)
    expiration_date = db.Column(db.DateTime)
    __tablename__ = 'session'


class Log(db.Model):
    # http://docs.pylonsproject.org/projects/pyramid_cookbook/en/latest/logging/sqlalchemy_logger.html
    id = db.Column(db.Integer, primary_key=True)
    logger = db.Column(db.String)
    level = db.Column(db.String)
    trace = db.Column(db.String)
    message = db.Column(db.String)
    path = db.Column(db.String)
    method = db.Column(db.String)
    ip = db.Column(db.String)
    is_admin = db.Column(db.String)
    creation_date = db.Column(db.DateTime, nullable=False, server_default=func.now())

    __table_args__ = ({'sqlite_autoincrement': True},)

class Category(BaseModel):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String, unique=True)
    url_name = db.Column(db.String, nullable=False, unique=True)
    description = db.Column(db.String, nullable=False)
    parent_id = db.Column(db.Integer, db.ForeignKey('category.id', ondelete='SET NULL'), nullable=True)
    creation_date = db.Column(db.DateTime, nullable=False, server_default=func.now())
    last_modified_date = db.Column(db.DateTime, nullable=True, server_default=func.now(), onupdate=func.now())
    __table_args__ = (db.CheckConstraint("name <> ''"), {'sqlite_autoincrement': True})

    def __repr__(self):
        return "Category(id={}, name='{}', parent_id={}".format(self.id, self.name, self.parent_id)


class Post(BaseModel):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='CASCADE'), nullable=False)
    title = db.Column(db.Unicode, nullable=False)
    url_name = db.Column(db.String, nullable=False, unique=True)  # www.matthewmoisen.com/blog/<url_name>/ # Also canonical meta
    description = db.Column(db.String, nullable=False)  # This it for the SEO html meta description
    # This represents the Main category to which this post belongs and will show up on home page
    category_id = db.Column(db.Integer, db.ForeignKey('category.id', ondelete='CASCADE'), nullable=False)
    content = db.Column(db.Unicode)
    is_published = db.Column(db.Boolean, default=False)
    creation_date = db.Column(db.DateTime, nullable=False, server_default=func.now())
    last_modified_date = db.Column(db.DateTime, nullable=True, server_default=func.now(), onupdate=func.now())
    is_commenting_disabled = db.Column(db.Boolean, nullable=False, default=False)


    __table_args__ = (db.CheckConstraint("title <> ''"),
                      (db.CheckConstraint("url_name <> ''")),
                      db.CheckConstraint("description <> ''"),
                      db.CheckConstraint("content <> ''"),
                      {'sqlite_autoincrement': True})

class Draft(BaseModel):
    id = db.Column(db.Integer, primary_key=True)
    # Original post id is null when we are createing a new post
    original_post_id = db.Column(db.Integer, db.ForeignKey('post.id', ondelete='CASCADE'), nullable=True)
    draft_post_id = db.Column(db.Integer, db.ForeignKey('post.id', ondelete='CASCADE'), nullable=False)

    __table_args__ = ((db.UniqueConstraint("original_post_id", "draft_post_id")),
                      {'sqlite_autoincrement': True},)


class Wordpress(BaseModel):
    id = db.Column(db.Integer, primary_key=True)
    type = db.Column(db.String, nullable=False)  # Image, guid, wordpress_url
    val = db.Column(db.String, nullable=False)
    redirect = db.Column(db.String, nullable=False)

    __table_args__ = (db.CheckConstraint("type in ('image', 'guid', 'url')"),
                      (db.UniqueConstraint("type", "val")),
                      {'sqlite_autoincrement': True}
                      )



class CategoryPost(BaseModel):
    id = db.Column(db.Integer, primary_key=True)
    category_id = db.Column(db.Integer, db.ForeignKey('category.id', ondelete='CASCADE'), nullable=False, index=True)
    post_id = db.Column(db.Integer, db.ForeignKey('post.id', ondelete='CASCADE'), nullable=False, index=True)

    __table_args__ = (
        (db.UniqueConstraint('category_id', 'post_id')),
        {'sqlite_autoincrement': True},
    )

class Comment(BaseModel):
    id = db.Column(db.Integer, primary_key=True)
    post_id = db.Column(db.Integer, db.ForeignKey('post.id', ondelete='CASCADE'), nullable=False)
    email = db.Column(db.String, nullable=True)
    name = db.Column(db.String, nullable=False)
    content = db.Column(db.Unicode, nullable=False)
    creation_date = db.Column(db.Date, nullable=False, server_default=func.now())
    is_approved = db.Column(db.Boolean, default=False, nullable=False)
    #parent_id = db.Column(db.Integer, db.ForeignKey('comment.id', ondelete='CASCADE'), nullable=True)

    __table_args__ = (db.CheckConstraint("content <> ''"), db.CheckConstraint("name <> ''"), {'sqlite_autoincrement': True})

class User(BaseModel):
    id = db.Column(db.Integer, primary_key=True)
    first_name = db.Column(db.String, nullable=False)
    last_name = db.Column(db.String, nullable=False)
    email = db.Column(db.String, nullable=False)
    password = db.Column(db.String, nullable=False)
    is_admin = db.Column(db.Boolean, nullable=False, default=False)

class Project(BaseModel):
    id = db.Column(db.Integer, primary_key=True)
    # TODO What happens if I delete the category to which this project belongs?
    # Do I want to delete cascade? I'll use to SET NULL for now
    category_id = db.Column(db.Integer, db.ForeignKey('category.id', ondelete='SET NULL'), nullable=False)

    __table_args__ = (
        {'sqlite_autoincrement': True},
    )

class ProjectPost(BaseModel):
    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey('project.id', ondelete='CASCADE'), nullable=False)
    post_id = db.Column(db.Integer, db.ForeignKey('post.id', ondelete='CASCADE'), nullable=False)
    # an order_no of 0 indicates the introduction post to the project and the /projects/<name>/ url will resolve there
    order_no = db.Column(db.Integer, nullable=False)

    __table_args__ = (
        db.UniqueConstraint('project_id', 'post_id'),
        # Should I enforce this at the DB layer or at the application layer ?
        db.UniqueConstraint('project_id', 'order_no'),
        {'sqlite_autoincrement': True},
    )


'''
class ProjectPostOrder(BaseModel):
    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey('project.id'), ondelete='CASCADE'), nullable=False)
    category_post_id = db.Column(db.Integer, db.ForeignKey('category_post.id', ondelete='CASCADE'), nullable=False)
    # an order_no of 0 indicates the introduction post to the project and the /projects/<name>/ url will resolve there
    order_no = db.Column(db.Integer, default=1, nullable=False)

    __table_args__ = (
        {'sqlite_autoincrement': True},
        # Should I enforce this at the DB layer or at the application layer ?
        (db.UniqueContraint('category_post_id', 'order_no')),
    )
'''