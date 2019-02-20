from functools import wraps
import time
import hashlib

from flask import g, make_response, render_template
from flask import request, abort

from .. import BansFrontend

def initialize(
		config,
		accounts,
		access_log,
		engine,
		install=False,
		connection=None,
	):
	g.bans = BansFrontend(
		config,
		accounts,
		access_log,
		engine,
		install=install,
		connection=connection,
	)

# require objects or abort
def require_ban(id):
	try:
		ban = g.bans.require_ban(id)
	except ValueError as e:
		abort(404, str(e))
	else:
		return ban

def require_not_banned(scope=''):
	# prevent admins from being caught in bans
	if g.bans.accounts.current_user:
		if g.bans.accounts.current_user.has_permission(group_names='admin'):
			return
		g.bans.last_checked_ban = g.bans.check_ban(
			remote_origin=request.remote_addr,
			user_id=g.bans.accounts.current_user.id_bytes,
			scope=scope,
		)
	else:
		g.bans.last_checked_ban = g.bans.check_ban(
			remote_origin=request.remote_addr,
			scope=scope,
		)
	if not g.bans.last_checked_ban:
		return
	if not g.bans.last_checked_ban.view_time:
		g.bans.update_ban(
			g.bans.last_checked_ban.id_bytes,
			view_time=time.time(),
		)
	abort(403, 'You are banned')
