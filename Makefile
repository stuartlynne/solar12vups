


all:

root_install:
	#sudo pip3 install .
	sudo pip install -U --force-reinstall .

root_uninstall:
	sudo pip3 uninstall -y solar12vups

user_install:
	pip3 install --user .
user_uninstall:
	pip3 uninstall -y solar12vups
