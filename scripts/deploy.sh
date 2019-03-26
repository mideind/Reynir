#! /bin/bash

# deploy.sh

# Deployment script for greynir.is

SRC=~/github/Reynir
DEST=/usr/share/nginx/greynir.is

echo "Deploying $SRC to $DEST..."

echo "Stopping greynir.is server"

sudo systemctl stop greynir

cd $DEST

echo "Upgrading the reynir package"

source p3510/bin/activate
pip install --upgrade -r requirements.txt
deactivate

cd $SRC

echo "Copying files"

cp config/Adjectives.conf $DEST/config/Adjectives.conf
cp config/Index.conf $DEST/config/Index.conf
# Note: config/Reynir.conf is not copied
cp config/TnT-model.pickle $DEST/config/TnT-model.pickle

cp article.py $DEST/article.py
cp correct.py $DEST/correct.py
cp fetcher.py $DEST/fetcher.py
cp geo.py $DEST/geo.py
cp images.py $DEST/images.py
# incparser.py is no longer needed
rm $DEST/incparser.py
cp main.py $DEST/main.py
cp nertokenizer.py $DEST/nertokenizer.py
cp postagger.py $DEST/postagger.py
cp processor.py $DEST/processor.py
cp query.py $DEST/query.py
cp scraper.py $DEST/scraper.py
cp -r db $DEST/
cp search.py $DEST/search.py
cp settings.py $DEST/settings.py
cp similar.py $DEST/similar.py
cp tnttagger.py $DEST/tnttagger.py
cp tree.py $DEST/tree.py
cp treeutil.py $DEST/treeutil.py
cp scrapers/*.py $DEST/scrapers/

# Processors are not required for the web server
# cp processors/*.py $DEST/processors/

rsync -av --delete templates/ $DEST/templates/
rsync -av --delete static/ $DEST/static/

cp resources/*.json $DEST/resources/

# Put a version identifier (date and time) into the about.html template
sed -i "s/\[Þróunarútgáfa\]/Útgáfa `date "+%Y-%m-%d %H:%M"`/g" $DEST/templates/about.html

echo "Deployment done"
echo "Starting greynir.is server..."

sudo systemctl start greynir