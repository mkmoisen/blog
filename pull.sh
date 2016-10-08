if [ $# -eq 0 ]
  then
     branch = "master"
  else
     branch = $1
fi

git pull origin $branch
pip install -r requirements.txt
sudo systemctl stop blog
python db_backup.py -db /apps/blog/blog/blog/db.db -b /apps/backups/
sudo systemctl start blog
nosetests
#python verify_sitemap.py