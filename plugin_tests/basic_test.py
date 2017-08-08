#!/usr/bin/env python
# -*- coding: utf-8 -*-

import json
import six
from tests import base


def setUpModule():
    base.enabledPlugins.append('wholetale')
    base.startServer()


def tearDownModule():
    base.stopServer()


class WholeTaleTestCase(base.TestCase):

    def setUp(self):
        super(WholeTaleTestCase, self).setUp()
        users = ({
            'email': 'root@dev.null',
            'login': 'admin',
            'firstName': 'Root',
            'lastName': 'van Klompf',
            'password': 'secret'
        }, {
            'email': 'joe@dev.null',
            'login': 'joeregular',
            'firstName': 'Joe',
            'lastName': 'Regular',
            'password': 'secret'
        })
        self.admin, self.user = [self.model('user').createUser(**user)
                                 for user in users]

    def testConfigValidators(self):
        from girder.plugins.wholetale.constants import PluginSettings
        resp = self.request('/system/setting', user=self.admin, method='PUT',
                            params={'key': PluginSettings.TMPNB_URL,
                                    'value': ''})
        self.assertStatus(resp, 400)
        self.assertEqual(resp.json, {
            'field': 'value',
            'type': 'validation',
            'message': 'TmpNB URL must not be empty.'
        })

        keys = {'PUB_KEY': PluginSettings.HUB_PUB_KEY,
                'PRIV_KEY': PluginSettings.HUB_PRIV_KEY}
        for k, v in six.iteritems(keys):
            params = {
                'key': v,
                'value': ''
            }
            resp = self.request('/system/setting', user=self.admin, method='PUT',
                                params=params)
            self.assertStatus(resp, 400)
            self.assertEqual(resp.json, {
                'field': 'value',
                'type': 'validation',
                'message': '%s must not be empty.' % k
            })

            params = {
                'key': v,
                'value': 'blah'
            }
            resp = self.request('/system/setting', user=self.admin, method='PUT',
                                params=params)
            self.assertStatus(resp, 400)
            self.assertEqual(resp.json, {
                'type': 'validation',
                'message': "%s's data structure could not be decoded." % k
            })

    def testListing(self):
        user = self.user
        c1 = self.model('collection').createCollection('c1', user)
        f1 = self.model('folder').createFolder(
            c1, 'f1', parentType='collection')
        i1 = self.model('item').createItem('i1', user, f1)
        i2 = self.model('item').createItem('i2', user, f1)
        assetstore = {'_id': 0}
        fl1 = self.model('file').createFile(user, i1, 'foo1', 7, assetstore)
        fl2 = self.model('file').createFile(user, i1, 'foo2', 13, assetstore)
        fl3 = self.model('file').createFile(user, i2, 'foo3', 19, assetstore)
        f2 = self.model('folder').createFolder(
            f1, 'f2', parentType='folder')
        i3 = self.model('item').createItem('i3', user, f2)
        self.model('file').createFile(user, i3, 'foo4', 23, assetstore)
        i4 = self.model('item').createItem('i4', user, f2)
        self.model('file').createFile(user, i4, 'foo5', 65535, assetstore)
        i5 = self.model('item').createItem('i5', user, f2)
        self.model('file').createFile(user, i5, 'foo6', 2.0 * 1024**8,
                                      assetstore)

        resp = self.request(
            path='/folder/{_id}/listing'.format(**f1), method='GET',
            user=user)
        self.assertStatusOk(resp)
        self.assertEqual(set(_['_id'] for _ in resp.json['files']),
                         set((str(fl3['_id']),)))
        self.assertEqual(set(_['_id'] for _ in resp.json['folders']),
                         set((str(f2['_id']), str(i1['_id']))))
        resp = self.request(
            path='/item/{_id}/listing'.format(**i1), method='GET',
            user=user)
        self.assertStatusOk(resp)
        self.assertEqual(resp.json['folders'], [])
        self.assertEqual(set(_['_id'] for _ in resp.json['files']),
                         set((str(fl1['_id']), str(fl2['_id']))))

    def testHubRoutes(self):
        from girder.plugins.wholetale.constants import PluginSettings
        self.model('setting').set(
            PluginSettings.TMPNB_URL, 'https://tmpnb.null')

        resp = self.request(path='/wholetale/genkey', user=self.admin,
                            method='POST')
        self.assertStatusOk(resp)
        self.assertIn(PluginSettings.HUB_PUB_KEY, resp.json)
        self.assertIn(PluginSettings.HUB_PRIV_KEY, resp.json)

        pubkey = resp.json[PluginSettings.HUB_PUB_KEY]

        resp = self.request(path='/wholetale', method='GET')
        self.assertStatusOk(resp)
        self.assertEqual(resp.json['url'], 'https://tmpnb.null')
        self.assertEqual(resp.json['pubkey'], pubkey)

    def testUserSettings(self):
        resp = self.request(path='/user/settings', method='GET')
        self.assertStatus(resp, 401)

        resp = self.request(
            path='/user/settings', method='PUT', user=self.user,
            type='application/json',
            body=json.dumps({'key1': 1, 'key2': 'value2'}))
        self.assertStatusOk(resp)
        self.assertEqual(resp.json['meta']['key1'], 1)
        self.assertEqual(resp.json['meta']['key2'], 'value2')

        resp = self.request(
            path='/user/settings', method='GET', user=self.user)
        self.assertStatusOk(resp)
        self.assertEqual(resp.json, {'key1': 1, 'key2': 'value2'})

        resp = self.request(
            path='/user/settings', method='PUT', user=self.user,
            type='application/json',
            body=json.dumps({'key1': 2, 'key2': None}))
        self.assertStatusOk(resp)
        self.assertEqual(resp.json['meta']['key1'], 2)
        self.assertNotIn('key2', resp.json['meta'])

    def testListingResources(self):
        user = self.user
        c1 = self.model('collection').createCollection('c1', user)
        f1 = self.model('folder').createFolder(
            c1, 'f1', parentType='collection')
        f2 = self.model('folder').createFolder(
            c1, 'f2', parentType='collection')
        i1 = self.model('item').createItem('i1', user, f1)
        i2 = self.model('item').createItem('i2', user, f1)

        data = {'item': [str(i1['_id']), str(i2['_id'])]}
        items = []
        for item in (i1, i2):
            resp = self.request(
                path='/item/{_id}'.format(**item), user=self.user)
            items.append(resp.json)

        resp = self.request(
            path='/resource', method='GET', user=self.user,
            params={'resources': json.dumps(data)})
        self.assertStatusOk(resp)
        self.assertEqual('folder' in resp.json, False)
        for iel, el in enumerate(resp.json['item']):
            for key in el:
                if key in ('lowerName', ):
                    continue
                self.assertEqual(el[key], items[iel][key])

        data = {'item': [str(i1['_id'])],
                'folder': [str(f1['_id']), str(f2['_id'])],
                'blah': []}
        folders = []
        for folder in (f1, f2):
            resp = self.request(
                path='/folder/{_id}'.format(**folder), user=self.user)
            folders.append(resp.json)

        resp = self.request(
            path='/resource', method='GET', user=self.user,
            params={'resources': json.dumps(data)})
        self.assertStatusOk(resp)
        self.assertEqual('item' in resp.json, True)
        for iel, el in enumerate(resp.json['folder']):
            for key in el:
                if key in ('lowerName', 'access'):
                    continue
                self.assertEqual(el[key], folders[iel][key])

        f3 = self.model('folder').createFolder(
            f1, 'f3', parentType='folder')
        self.model('item').createItem('i1', user, f3)
        self.model('item').createItem('i2', user, f3)

        resp = self.request(
            path='/folder/{_id}/datamap'.format(**f1), user=self.user)
        self.assertStatusOk(resp)
        self.assertEqual({_['mountPoint'] for _ in resp.json},
                         {'/i1', '/i2', '/f3/i1', '/f3/i2'})
