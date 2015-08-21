import asyncio
import logging
import json
import os
from aiohttp import web
import aiohttp_jinja2
import jinja2
from aiohttp_ac_hipchat.addon import create_addon_app
from aiohttp_ac_hipchat.addon import require_jwt
from aiohttp_ac_hipchat.util import allow_cross_origin, http_request
from aiohttp_ac_hipchat.webhook import RoomNotificationArgumentParser, HtmlNotification

GLANCE_MODULE_KEY = "hcalias.glance"

log = logging.getLogger(__name__)
app = create_addon_app(plugin_key="hc-alias",
                       addon_name="HC Alias",
                       from_name="Alias")

aiohttp_jinja2.setup(app, autoescape=True,
                     loader=jinja2.FileSystemLoader(os.path.join(os.path.dirname(__file__), 'views')))


@asyncio.coroutine
def init(app):
    @asyncio.coroutine
    def _send_welcome(event):
        client = event['client']
        yield from client.send_notification(app['addon'], text="HC Alias was added to this room")
        parser = _create_parser(client)
        parser.send_usage()
        yield from parser.task

    app['addon'].register_event('install', _send_welcome)


app.add_hook('before_first_request', init)


def capabilities(request):
    config = request.app["config"]
    base_url = config["BASE_URL"]
    response = web.Response(text=json.dumps({
        "links": {
            "self": base_url,
            "homepage": base_url
        },
        "key": config.get("PLUGIN_KEY"),
        "name": config.get("ADDON_NAME"),
        "description": "HipChat connect add-on that sends supports aliases for group mention",
        "vendor": {
            "name": "Atlassian Labs",
            "url": "https://atlassian.com"
        },
        "capabilities": {
            "installable": {
                "allowGlobal": False,
                "allowRoom": True,
                "callbackUrl": base_url + "/installable"
            },
            "hipchatApiConsumer": {
                "scopes": [
                    "view_group",
                    "view_room",
                    "send_notification",
                    "admin_room"
                ],
                "fromName": config.get("FROM_NAME")
            },
            "webhook": [
                {
                    "url": base_url + "/alias",
                    "event": "room_message",
                    "pattern": "^/alias(\s|$).*"
                }
            ],
            "glance": [
                {
                    "key": GLANCE_MODULE_KEY,
                    "name": {
                        "value": "Alias"
                    },
                    "queryUrl": base_url + "/glance",
                    "target": "hcalias.sidebar",
                    "icon": {
                        "url": base_url + "/static/at.png",
                        "url@2x": base_url + "/static/at@2x.png"
                    }
                }
            ],
            "webPanel": [
                {
                    "key": "hcalias.sidebar",
                    "name": {
                        "value": "Aliases"
                    },
                    "location": "hipchat.sidebar.right",
                    "url": base_url + "/alias_list"
                }
            ]
        }
    }))
    return response


@asyncio.coroutine
@require_jwt(app)
@allow_cross_origin
def get_glance(request):
    aliases = yield from find_all_alias(request.client)
    return web.Response(text=json.dumps(glance_json(len(aliases))))


@asyncio.coroutine
def update_glance(client, room):
    aliases = yield from find_all_alias(client)
    yield from push_glance_update(client, room, {
        "glance": [{
            "key": GLANCE_MODULE_KEY,
            "content": glance_json(len(aliases))
        }]
    })

def glance_json(count):
    return {
        "label": {
            "type": "html",
            "value": "Alias"
        },
        "status": {
            "type": "lozenge",
            "value": {
                "label": "{}".format(count),
                "type": "success"
            }
        }
    }

@asyncio.coroutine
def push_glance_update(client, room_id_or_name, glance):
    token = yield from client.get_token(app['redis_pool'], scopes=['view_room'])
    with (yield from http_request('POST', "%s/addon/ui/room/%s" % (client.api_base_url, room_id_or_name),
                                  headers={'content-type': 'application/json',
                                           'authorization': 'Bearer %s' % token},
                                  data=json.dumps(glance),
                                  timeout=10)) as resp:
        if resp.status == 204:
            log.debug('Glance update pushed')
        else:
            log.error(resp.status)
            body = yield from resp.read()
            log.error(body)


@asyncio.coroutine
@require_jwt(app)
@allow_cross_origin
@aiohttp_jinja2.template('aliases.html')
def get_alias_list(request):
    aliases = yield from find_all_alias(request.client)

    return {
        "aliases": aliases,
        "signed_request": request.signed_request,
        "room": request.client.room_id
    }


@asyncio.coroutine
@require_jwt(app)
@allow_cross_origin
def create_mention(request):
    data = yield from request.json()
    success = yield from set_alias(request.client, data['room'], data['alias'], data['mentions'])
    if success:
        return web.Response(status=204)
    else:
        return web.Response(status=500, text="Failed to set alias")

@asyncio.coroutine
def alias(request):
    addon = request.app['addon']
    body = yield from request.json()
    client_id = body['oauth_client_id']
    client = yield from addon.load_client(client_id)

    parser = _create_parser(client)

    result = yield from parser.handle_webhook(body)
    return web.Response(status=204, text=result)


@asyncio.coroutine
def mention(request):
    alias_name = request.match_info['alias_name']
    addon = request.app['addon']
    body = yield from request.json()
    client_id = body['oauth_client_id']
    client = yield from addon.load_client(client_id)

    existing = yield from find_alias(client, alias_name)
    if existing:
        mentions = existing['mentions']

        txt = "said: {original} /cc {mentions}".format(
            original=body['item']["message"]["message"],
            mentions=" ".join(mentions))
        from_mention = body['item']['message']['from']['mention_name']
        yield from client.send_notification(addon, from_mention=from_mention, text=txt)
        return web.Response(status=204)
    else:
        log.error("Mention name '%s' not found for client %s" % (alias_name, client_id))
        return web.Response(status=400)


@asyncio.coroutine
def find_alias(client, name):
    result = yield from _aliases_db().find_one({
        "client_id": client.id,
        "group_id": client.group_id,
        "capabilities_url": client.capabilities_url,
        "alias": name
    })
    return result


@asyncio.coroutine
def find_all_alias(client):
    results = yield from _aliases_db().find({
        "client_id": client.id,
        "group_id": client.group_id,
        "capabilities_url": client.capabilities_url
    })
    return results


@asyncio.coroutine
def find_aliases_for_room(request):
    room_id = str(request.match_info['room_id'])
    results = yield from _aliases_db().find({'room_id': room_id})
    resp_body = {}
    if results:
        for item in results:
            resp_body[item['alias']] = item['mentions']

    return web.Response(text=json.dumps(resp_body), content_type='application/json')


def create_webhook_pattern(alias):
    return "(?:(?:^[^/]|\/[^a]|\/a[^l]|\/ali[^a]|\/alia[^s]).*|^)%s(?:$| ).*" % alias


@asyncio.coroutine
def set_alias(client, room, alias_name, mentions):
    try:
        for item in mentions + [alias_name]:
            validate_mention_name(item)
    except ValueError as e:
        return str(e)

    existing = yield from find_alias(client, alias_name)
    if existing and 'webhook_url' in existing:
        yield from client.delete_webhook(app['addon'], existing['webhook_url'])

    webhook_url = yield from client.post_webhook(app['addon'],
                                                 url="%s/mention/%s" % (app['config']['BASE_URL'], alias_name),
                                                 pattern=create_webhook_pattern(alias_name),
                                                 name="Alias {}".format(alias_name))
    if webhook_url:
        aliases = _aliases_db()
        spec = {
            "client_id": client.id,
            "group_id": client.group_id,
            "capabilities_url": client.capabilities_url,
            "alias": alias_name
        }
        data = {
            'mentions': mentions,
            'webhook_url': webhook_url,
            'room_id': room
        }
        if existing:
            existing.update(data)
            yield from aliases.update(spec, existing)
        else:
            data.update(spec)
            yield from aliases.insert(data)
            yield from update_glance(client, room)
        return True
    else:
        return False

def _create_parser(client):
    @asyncio.coroutine
    def list_aliases(_):
        aliases = yield from find_all_alias(client)
        if not aliases:
            return "No aliases registered. Register one with '/alias set @ALIAS @MENTION...'"
        else:
            return "Aliases registered: %s" % ", ".join([a['alias'] for a in aliases])

    @asyncio.coroutine
    def set_alias_handler(args):
        success = yield from set_alias(client, args.room, args.alias, args.mentions)
        if success:
            return 'Alias {} added'.format(args.alias)
        else:
            return "Problem creating alias"


    @asyncio.coroutine
    def add_to(args):
        alias_text = args.alias

        existing_alias = yield from find_alias(client, alias_text)
        if not existing_alias:
            return "The alias you're trying to update ({}) to does not exists. BETTER MESSAGE HERE".format(alias_text)

        new_mentions = args.mentions

        try:
            for item in new_mentions:
                validate_mention_name(item)
        except ValueError as e:
            return str(e)

        existing_alias['mentions'] = list(set(existing_alias['mentions'] + new_mentions))

        spec = {
            "client_id": client.id,
            "group_id": client.group_id,
            "capabilities_url": client.capabilities_url,
            "alias": alias_text
        }

        yield from _aliases_db().update(spec, existing_alias)
        return "Added {} to {}".format(', '.join(new_mentions), alias_text)

    @asyncio.coroutine
    def remove_from(args):
        alias_text = args.alias

        existing_alias = yield from find_alias(client, alias_text)
        if not existing_alias:
            return "The alias you're trying to update ({}) to does not exists. BETTER MESSAGE HERE".format(alias_text)

        for m in args.mentions:
            if m in existing_alias['mentions']:
                existing_alias['mentions'].remove(m)

        spec = {
            "client_id": client.id,
            "group_id": client.group_id,
            "capabilities_url": client.capabilities_url,
            "alias": alias_text
        }

        yield from _aliases_db().update(spec, existing_alias)
        return "Removed {} from {}".format(', '.join(args.mentions), alias_text)

    @asyncio.coroutine
    def delete_alias(args):
        try:
            validate_mention_name(args.alias)
        except ValueError as e:
            return str(e)

        existing = yield from find_alias(client, args.alias)
        if existing and 'webhook_url' in existing:
            yield from client.delete_webhook(app['addon'], existing['webhook_url'])
            yield from _aliases_db().remove(existing)
            yield from update_glance(client, args.room)
            return "Alias %s deleted" % args.alias
        else:
            return "Alias %s not found" % args.alias

    @asyncio.coroutine
    def show_alias(args):
        try:
            validate_mention_name(args.alias)
        except ValueError as e:
            return str(e)

        existing = yield from find_alias(client, args.alias)
        if existing and 'webhook_url' in existing:
            mentions = ['&commat;%s' % x[1:] for x in existing['mentions']]
            return HtmlNotification("Alias %s is mapped to %s" % (args.alias, ", ".join(mentions)))
        else:
            return "Alias %s not found" % args.alias

    parser = RoomNotificationArgumentParser(app, "/alias", client)
    parser.add_argument('room', type=int)
    subparsers = parser.add_subparsers(help='Available commands')

    subparsers.add_parser('list', help='List existing aliases', handler=list_aliases)

    parser_set = subparsers.add_parser('set', help='Sets a group mention alias', handler=set_alias_handler)
    parser_set.add_argument('alias', metavar='@ALIAS', type=str, help='The mention alias, beginning with an "@"')
    parser_set.add_argument('mentions', metavar='@MENTION', nargs='+', type=str,
                            help='The mention names, beginning with an "@"')

    parser_delete = subparsers.add_parser('delete', help='Deletes a group mention alias', handler=delete_alias)
    parser_delete.add_argument('alias', metavar='@ALIAS', type=str, help='The mention alias, beginning with an "@"')

    parser_show = subparsers.add_parser('show', help='Shows the names for an existing alias', handler=show_alias)
    parser_show.add_argument('alias', metavar='@ALIAS', type=str, help='The mention alias, beginning with an "@"')

    parser_add_to = subparsers.add_parser('add_to', help='Add a mention to an existing alias', handler=add_to)
    parser_add_to.add_argument('alias', metavar='@ALIAS', type=str, help='The mention alias, beginning with an "@"')
    parser_add_to.add_argument('mentions', metavar='@MENTION', nargs='+', type=str,
                               help='The mention names, beginning with an "@"')

    parser_remove_from = subparsers.add_parser('remove_from', help='Remove a mention from an existing alias',
                                               handler=remove_from)
    parser_remove_from.add_argument('alias', metavar='@ALIAS', type=str,
                                    help='The mention alias, beginning with an "@"')
    parser_remove_from.add_argument('mentions', metavar='@MENTION', nargs='+', type=str,
                                    help='The mention names, beginning with an "@"')

    return parser


invalid_mention_name_chars = '<>~!@#$%^&*()=+[]{}\\|:;\'"/,.-_'


def validate_mention_name(mention_name: str):
    """
    Validates a mention name, throwing a ValueError if invalid.
    """

    if mention_name is None:
        raise ValueError("The mention name is required")

    if not mention_name.startswith("@"):
        raise ValueError("The mention name must begin with a '@'")

    if not 0 < len(mention_name) < 50:
        raise ValueError("The mention name must be between 0 and 50 characters")

    name = mention_name[1:]
    if name in ["all", "aii", "hipchat"]:
        raise ValueError("The mention name is not valid")

    if any(x in name for x in invalid_mention_name_chars):
        raise ValueError("The mention name cannot contain certain characters: %s" %
                         invalid_mention_name_chars)
    if ' ' in name:
        raise ValueError("The mention name cannot contain multiple words")

def _aliases_db():
    return app['mongodb'].default_database['aliases']


app.router.add_static('/static', os.path.join(os.path.dirname(__file__), 'static'), name='static')
app.router.add_route('GET', '/', capabilities)
app.router.add_route('GET', '/glance', get_glance)
app.router.add_route('GET', '/alias_list', get_alias_list)
app.router.add_route('POST', '/alias', alias)
app.router.add_route('POST', '/mention/{alias_name}', mention)
app.router.add_route('POST', '/create', create_mention)
app.router.add_route('GET', '/room/{room_id}/alias', find_aliases_for_room)
