from blog import app, db
from functools import wraps
from flask import jsonify, abort, render_template
from sqlalchemy.orm.exc import NoResultFound

date_format = '%Y-%m-%dT%H:%M:%S.%fZ'

class ServerError(Exception):
    pass

class UserError(Exception):
    pass

def try_except(api=False):
    def real_decorator(func):
        @wraps(func)
        def _try_except(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except NoResultFound as ex:
                app.logger.exception("NoResultFound in {}".format(func.__name__))
                db.session.rollback()
                if not api:
                    abort(404)
            except UserError as ex:
                app.logger.exception("UserError in {}: {}".format(func.__name__, ex.message))
                db.session.rollback()
                if not api:
                    abort(400)
                return jsonify({"error": ex.message}), 400
            except ServerError as ex:
                app.logger.exception("ServerError in {}: {}".format(func.__name__, ex.message))
                db.session.rollback()
                if not api:
                    abort(400)
                return jsonify({"error": ex.message}), 500
            except Exception as ex:
                app.logger.exception("Exception in {}: {}".format(func.__name__, ex.message))
                import time
                app.logger.debug("SLEEPING IN TRY EXCEPT")
                time.sleep(10)
                db.session.rollback()
                if not api:
                    abort(500)
                return jsonify({"error": ex.message}), 500
        return _try_except
    return real_decorator

@app.errorhandler(404)
def page_not_found(error):
    app.logger.debug("I AM 404 LOL")
    return render_template('404.html')

@app.errorhandler(500)
def server_error(error):
    app.logger.debug("I AM 500 LOL")
    return render_template('500.html')

@app.context_processor
def inject_global_vars():
    return {
        'web_protocol': app.config['WEB_PROTOCOL']
    }

'''
def try_except(func):
    @wraps(func)
    def _try_except(*args, **kwargs):
        try:
            app.logger.debug("In {}, args={}, kwargs={}".format(func.func_name, args, kwargs))
            return func(*args, **kwargs)

        except BadRequest as ex:
            app.logger.exception(ex)
            return jsonify({'error': 'Invalid JSON request {}'.format(ex.message)}), 400

        except UserError as ex:
            app.logger.exception(ex.message)
            db.session.rollback()
            return jsonify({'error': ex.message}), 400

        except ServerError as ex:
            app.logger.exception(ex.message)
            db.session.rollback()
            return jsonify({'error': ex.message}), 500

        except SQLAlchemyError as ex:
            #This is a server error
            app.logger.exception(ex.message)
            db.session.rollback()
            return jsonify({'error': ex.message}), 500

        except Exception as ex:
            app.logger.exception(ex.message)
            db.session.rollback()
            return jsonify({'error': ex.message}), 500

    return _try_except
'''
import home