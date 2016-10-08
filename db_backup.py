#!/usr/bin/env python
"""
A script to backup the sqlite database for my blog
Heavily influenced by http://codereview.stackexchange.com/questions/78643/create-sqlite-backups
CRON
Run at 2am every day
0 2 * * * /apps/blog/bin/python /apps/blog/blog/db_backup.py -db /apps/blog/blog/blog/db.db -b /apps/backups/

# Testing on stage
0 2 * * * /apps/stage/bin/python /apps/stage/blog/db_backup.py -db /apps/stage/blog/blog/db.db -b /apps/backups/stage

"""

import sqlite3
import shutil
from datetime import datetime
import os
import argparse
import sys
import logging.handlers
import logging
import hashlib


logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
formatter = logging.Formatter('%(asctime)s %(name)-12s %(levelname)-8s %(message)s')

handler = logging.StreamHandler()
handler.setFormatter(formatter)
logger.addHandler(handler)

handler2 = logging.handlers.RotatingFileHandler(os.path.join(os.path.split(os.path.abspath(__file__))[0], 'db_backup.log'),
                                        maxBytes=10*1024*1024, backupCount=2)
handler2.setFormatter(formatter)
logger.addHandler(handler2)


parser = argparse.ArgumentParser()
parser.add_argument("-db", "--database")
parser.add_argument("-b", "--backup_dir")
parser.add_argument("-dt", "--datetime", default=None)

def get_hash(file_path):
    # http://stackoverflow.com/a/3431838/1391717
    hash_sha1 = hashlib.sha1()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            hash_sha1.update(chunk)

    return hash_sha1.hexdigest()

def _file_to_date(file_name):
    return file_name.split('_', 1)[1][:-4]

def find_latest_backup(backup_dir):
    max = None
    last_backup = None
    for file_name in os.listdir(backup_dir):
        dt = _file_to_date(file_name)
        if max is None or dt > max:
            max = dt
            last_backup = file_name

    return last_backup

def get_args():
    args = parser.parse_args()
    if args.datetime is None:
        args.datetime = datetime.utcnow()

    return args

def backup(args):
    if not os.path.isdir(args.backup_dir):
        raise ValueError("Backup directory does not exist: {}".format(args.backup_dir))

    if not os.path.isfile(args.database):
        raise ValueError("Database file does not exist: {}".format(args.database))

    last_backup = find_latest_backup(args.backup_dir)

    backup_file = os.path.join(args.backup_dir, os.path.basename(args.database) + "_" + args.datetime.strftime("%Y-%m-%d_%H.%M.%S") + ".bck")

    connection = sqlite3.connect(args.database)
    try:
        cursor = connection.cursor()
        cursor.execute("begin immediate")

        last_backup_hash = None
        if last_backup is not None:
            last_backup_hash = get_hash(os.path.join(args.backup_dir, last_backup))

        db_hash = get_hash(args.database)

        if last_backup_hash != db_hash:
            shutil.copyfile(args.database, backup_file)
    except Exception:
        connection.rollback()
        raise

def main():
    args = get_args()
    logger.info(args)

    backup(args)

if __name__ == '__main__':
    try:
        main()
    except Exception as ex:
        logger.exception("Failed to backup: {}".format(ex))
        sys.exit(1)
    else:
        logger.info("Backup successful")
        sys.exit(0)
