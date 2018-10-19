import time

from bans import Bans

class BansFrontend(Bans):
	def __init__(self, config, accounts, access_log, engine, install=False):
		super().__init__(engine, config['db_prefix'], install)

		self.config = config
		self.accounts = accounts
		self.access_log = access_log

		self.callbacks = {}

	def add_callback(self, name, f):
		if name not in self.callbacks:
			self.callbacks[name] = []
		self.callbacks[name].append(f)

	# require object or raise
	def require_ban(self, id):
		ban = self.get_ban(id)
		if not ban:
			raise ValueError('Ban not found')
		return ban

	# extend bans methods
	def get_ban(self, ban_id):
		ban = super().get_ban(ban_id)
		if ban:
			user_ids = []
			if ban.created_by_user_id:
				user_ids.append(ban.created_by_user_id)
			if ban.user_id:
				user_ids.append(ban.user_id)
			users = self.accounts.search_users(filter={'ids': user_ids})
			if ban.created_by_user_id:
				ban.created_by_user = users.get(ban.created_by_user_id_bytes)
			if ban.user_id in users:
				ban.user = users.get(ban.user_id_bytes)
		return ban

	def search_bans(self, **kwargs):
		bans = super().search_bans(**kwargs)
		user_ids = []
		for ban in bans.values():
			if ban.created_by_user_id:
				user_ids.append(ban.created_by_user_id)
			if ban.user_id:
				user_ids.append(ban.user_id)
		users = self.accounts.search_users(filter={'ids': user_ids})
		for ban in bans.values():
			if ban.created_by_user_id:
				ban.created_by_user = users.get(ban.created_by_user_id_bytes)
			if ban.user_id in users:
				ban.user = users.get(ban.user_id_bytes)
		return bans

	def create_ban(self, **kwargs):
		ban = super().create_ban(**kwargs)
		subject_id = ''
		if ban.created_by_user_id:
			subject_id = ban.created_by_user_id
		self.access_log.create_log(
			scope='create_ban',
			subject_id=subject_id,
			object_id=ban.id,
		)
		return ban

	def delete_ban(self, ban, user_id):
		super().delete_ban(ban.id_bytes)
		self.access_log.create_log(
			scope='delete_ban',
			subject_id=user_id,
			object_id=ban.id_bytes,
		)

	def prune_bans(self, expired_before=None, user_id=''):
		expired_before = (
			time.time() - self.config['expired_ban_review_lifetime']
		)
		super().prune_bans(expired_before=expired_before)
		self.access_log.create_log(
			scope='prune_bans',
			subject_id=user_id,
		)

