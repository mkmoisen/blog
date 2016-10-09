"""
Pull script to promote code to stage or prod
"""
import argparse
import subprocess
import sys
import logging
import time

logging.basicConfig()
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

parser = argparse.ArgumentParser()

parser.add_argument("-e", "--environment", choices=['stage', 'prod'], required=True)
parser.add_argument("-b", "--branch", default='master')


def proc(command):
    command = command.split(' ')
    p = subprocess.Popen(command, stdout=subprocess.PIPE)
    stdout, stderr = p.communicate()
    return stdout, stderr, p.returncode

def git_pull(branch):
    command = 'git pull origin {}'.format(branch)
    stdout, stderr, code = proc(command)
    if code != 0:
        raise ValueError(stderr)

def pip_install():
    command = 'pip install -r requirements.txt'
    stdout, stderr, code = proc(command)
    if code != 0:
        raise ValueError(stderr)

def stop_blog(environment):
    service = 'blog_stage'
    if environment == 'prod':
        service = 'blog'
    command = 'systemctl stop {}'.format(service)
    stdout, stderr, code = proc(command)
    if environment == 'prod' and code != 0:
        raise ValueError(stderr)
    return stdout, stderr, code

def backup_db(environment):
    db = '/apps/stage/blog/blog/db.db'
    b = '/apps/backups/stage/'
    if environment == 'prod':
        db = '/apps/blog/blog/blog/db.db'
        b = '/apps/backups/'
    command = 'python db_backup.py -db {} -b {}'.format(db, b)
    stdout, stderr, code = proc(command)
    if code != 0:
        raise ValueError(stderr)

def nosetests():
    command = 'nosetests'
    stdout, stderr, code = proc(command)
    if code != 0:
        raise ValueError(stderr)

def start_blog(environment):
    service = 'blog_stage'
    if environment == 'prod':
        service = 'blog'
    command = 'systemctl start {}'.format(service)
    stdout, stderr, code = proc(command)
    if code != 0:
        raise ValueError(stderr)

def verify_sitemap():
    command = 'python verify_sitemap.py'
    stdout, stderr, code = proc(command)
    if code != 0:
        raise ValueError(stderr)

def main():
    args = parser.parse_args()
    git_pull(args.branch)
    pip_install()
    stop_blog(args.environment)
    backup_db(args.environment)
    nosetests()
    start_blog(args.environment)
    time.sleep(2)
    verify_sitemap()


if __name__ == "__main__":
    try:
        main()
    except Exception as ex:
        logger.exception("Failed: {}".format(ex))
        sys.exit(1)
    else:
        logger.info("Pull successful")
        sys.exit(0)