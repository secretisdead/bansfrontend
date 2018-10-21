import math
import json
import urllib
import time

from ipaddress import ip_address
from flask import Blueprint, render_template, abort, request, redirect
from flask import url_for, g
import dateutil.parser

from pagination_from_request import pagination_from_request
from . import require_ban
from accounts.views import require_permissions

bans_manager = Blueprint(
	'bans_manager',
	__name__,
	template_folder='templates',
)

@bans_manager.route('/bans/create', methods=['GET', 'POST'])
@require_permissions(group_names='manager')
def create_ban():
	if 'POST' != request.method:
		return render_template('create_ban.html')
	for field in [
			'duration',
			'scope',
			'reason',
			'note',
			'remote_origin',
			'user_id',
		]:
		if field not in request.form:
			abort(400, 'Missing ban creation fields')
	errors = []
	user_id = ''
	opts = {}
	if request.form['user_id']:
		try:
			user = g.bans.accounts.require_user(id=request.form['user_id'])
		except ValueError as e:
			errors.append(str(e))
		else:
			user_id = user.id_bytes
	if request.form['remote_origin']:
		try:
			remote_origin = ip_address(request.form['remote_origin'])
		except ValueError:
			errors.append('Invalid remote origin')
		else:
			opts['remote_origin'] = remote_origin.exploded
	if 0 == request.form['duration'] or '0' == request.form['duration']:
		expiration_time = 0
	else:
		try:
			duration = int(request.form['duration'])
		except ValueError:
			errors.append('Invalid duration')
		else:
			expiration_time = (time.time() + duration)
	if not request.form['user_id'] and not request.form['remote_origin']:
		errors.append('Missing both user ID and remote origin')
	if not errors:
		g.bans.create_ban(
			scope=request.form['scope'],
			reason=request.form['reason'],
			note=request.form['note'],
			expiration_time=expiration_time,
			created_by_user_id=g.bans.accounts.current_user.id_bytes,
			user_id=user_id,
			**opts
		)
		return redirect(url_for('bans_manager.bans_list'), code=303)
	return render_template(
		'create_ban.html',
		errors=errors,
		#TODO pass in posted values for form fields
		#TODO so they can be preserved after errors
	)

@bans_manager.route('/bans/prune')
@require_permissions(group_names='manager')
def prune_bans():
	#TODO this probably belongs in a cronjob
	# but for now manually triggering prune of expired bans older than review
	# period is fine
	g.bans.prune_bans(user_id=g.bans.accounts.current_user.id_bytes)
	return redirect(url_for('bans_manager.bans_list'), code=303)

@bans_manager.route('/bans/<ban_id>/remove')
@require_permissions(group_names='manager')
def remove_ban(ban_id):
	ban = require_ban(ban_id)
	g.bans.delete_ban(ban, g.bans.accounts.current_user.id_bytes)
	if 'redirect_uri' in request.args:
		return redirect(request.args['redirect_uri'], code=303)
	return redirect(url_for('bans_manager.bans_list'), code=303)

@bans_manager.route('/bans')
@require_permissions(group_names='manager')
def bans_list():
	search = {
		'id': '',
		'created_before': '',
		'created_after': '',
		'remote_origin': '',
		'scope': '',
		'reason': '',
		'note': '',
		'expired_before': '',
		'expired_after': '',
		'viewed_after': '',
		'viewed_before': '',
		'created_by_user_id': '',
		'user_id': '',
	}
	for field in search:
		if field in request.args:
			search[field] = request.args[field]

	filter = {}
	escape = lambda value: (
		value
			.replace('\\', '\\\\')
			.replace('_', '\_')
			.replace('%', '\%')
			.replace('-', '\-')
	)
	# for parsing datetime and timestamp from submitted form
	# filter fields are named the same as search fields
	time_fields = [
		'created_before',
		'created_after',
		'expired_before',
		'expired_after',
		'viewed_before',
		'viewed_after',
	]
	for field, value in search.items():
		if not value:
			continue
		if 'id' == field:
			filter['ids'] = value
		elif field in time_fields:
			try:
				parsed = dateutil.parser.parse(value)
			except ValueError:
				filter[field] = 'bad_query'
			else:
				search[field] = parsed.strftime('%Y-%m-%dT%H:%M:%S.%f%z')
				filter[field] = parsed.timestamp()
		elif 'remote_origin' == field:
			filter['with_remote_origins'] = value
		elif 'scope' == field:
			if 'global' == value:
				value = ''
			filter['scopes'] = value
		elif 'reason' == field:
			filter['reasons'] = '%' + escape(value) + '%'
		elif 'note' == field:
			filter['notes'] = '%' + escape(value) + '%'
		elif 'created_by_user_id' == field:
			if 'system' == value:
				value = ''
			filter['created_by_user_ids'] = value
		elif 'user_id' == field:
			filter['user_ids'] = value

	pagination = pagination_from_request('creation_time', 'desc', 0, 32)

	total_results = g.bans.count_bans(filter=filter)
	results = g.bans.search_bans(filter=filter, **pagination)

	# enhanced search for users
	ids = []
	for ban in results.values():
		if ban.created_by_user_id:
			ids.append(ban.created_by_user_id)
		if ban.user_id:
			ids.append(ban.user_id)
	users = g.bans.accounts.search_users(filter={'ids': ids})
	for ban in results.values():
		if ban.created_by_user_id in users:
			ban.created_by_user = users.get(ban.created_by_user_id)
		if ban.user_id in users:
			ban.user = users.get(ban.user_id)

	return render_template(
		'bans_list.html',
		results=results,
		search=search,
		pagination=pagination,
		total_results=total_results,
		total_pages=math.ceil(total_results / pagination['perpage']),
		unique_scopes=g.bans.get_unique_scopes(),
	)
