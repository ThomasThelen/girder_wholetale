# -*- coding: utf-8 -*-

import datetime

from bson.objectid import ObjectId

from ..constants import WORKSPACE_NAME, DATADIRS_NAME
from ..utils import getOrCreateRootFolder
from girder.models.model_base import AccessControlledModel
from girder.models.folder import Folder
from girder.models.user import User
from girder.constants import AccessType
from girder.exceptions import \
    GirderException, ValidationException


# Whenever the Tale object schema is modified (e.g. fields are added or
# removed) increase `_currentTaleFormat` to retroactively apply those
# changes to existing Tales.
_currentTaleFormat = 2


class Tale(AccessControlledModel):

    def initialize(self):
        self.name = 'tale'
        self.ensureIndices(('imageId', ([('imageId', 1)], {})))
        self.ensureTextIndex({
            'title': 10,
            'description': 1
        })
        self.modifiableFields = {
            'title', 'description', 'public', 'config', 'updated', 'authors',
            'category', 'icon', 'iframe', 'illustration'
        }
        self.exposeFields(
            level=AccessType.READ,
            fields=({'_id', 'folderId', 'imageId', 'creatorId', 'created',
                     'format', 'data'} | self.modifiableFields))
        self.exposeFields(level=AccessType.ADMIN, fields={'published'})

    def validate(self, tale):
        if 'iframe' not in tale:
            tale['iframe'] = False
        if tale.get('format', 0) < 2:
            dataFolder = getOrCreateRootFolder(DATADIRS_NAME)
            try:
                origFolder = Folder().load(tale['folderId'], force=True, exc=True)
            except ValidationException:
                raise GirderException(
                    'Tale ({_id}) references folder ({folderId}) that does not exist'.format(**tale))
            if origFolder.get('creatorId'):
                creator = User().load(origFolder['creatorId'], force=True)
            else:
                creator = None
            tale['data'] = {'type': 'folder', 'id': tale.pop('folderId')}
            newFolder = Folder().copyFolder(
                origFolder, parent=dataFolder, name=str(tale['_id']),
                creator=creator, progress=False)
            tale['folderId'] = newFolder['_id']
        tale['format'] = _currentTaleFormat
        return tale

    def setPublished(self, tale, publish, save=False):
        assert isinstance(publish, bool)
        tale['published'] = publish or tale['published']
        if save:
            tale = self.save(tale)
        return tale

    def list(self, user=None, folder=None, image=None, limit=0, offset=0,
             sort=None, currentUser=None):
        """
        List a page of jobs for a given user.

        :param user: The user who created the tale.
        :type user: dict or None
        :param folder: The folder that's being used by the tale.
        :type folder: dict or None
        :param image: The Image that's being used by the tale.
        :type image: dict or None
        :param limit: The page limit.
        :param offset: The page offset
        :param sort: The sort field.
        :param currentUser: User for access filtering.
        """
        cursor_def = {}
        if user is not None:
            cursor_def['creatorId'] = user['_id']
        if folder is not None:
            cursor_def['folderId'] = folder['_id']
        if image is not None:
            cursor_def['imageId'] = image['_id']

        cursor = self.find(cursor_def, sort=sort)
        for r in self.filterResultsByPermission(
                cursor=cursor, user=currentUser, level=AccessType.READ,
                limit=limit, offset=offset):
            yield r

    def createTale(self, image, folder, creator=None, save=True, title=None,
                   description=None, public=None, config=None, published=False,
                   authors=None, icon=None, category=None, illustration=None,
                   iframe=False):
        if creator is None:
            creatorId = None
        else:
            creatorId = creator.get('_id', None)

        if title is None:
            title = '{} with {}'.format(image['fullName'], folder['name'])
        # if illustration is None:
            # Get image from SILS

        now = datetime.datetime.utcnow()
        tale = {
            'authors': authors,
            'category': category,
            'config': config,
            'creatorId': creatorId,
            'description': description,
            'folderId': ObjectId(folder['_id']),
            'format': _currentTaleFormat,
            'created': now,
            'icon': icon,
            'iframe': iframe,
            'imageId': ObjectId(image['_id']),
            'illustration': illustration,
            'title': title,
            'public': public,
            'published': published,
            'updated': now
        }
        if public is not None and isinstance(public, bool):
            self.setPublic(tale, public, save=False)
        else:
            public = False

        if creator is not None:
            self.setUserAccess(tale, user=creator, level=AccessType.ADMIN,
                               save=False)
        if save:
            tale = self.save(tale)
            self.createWorkspace(tale, creator=creator)
        return tale

    def createDataMountpoint(self, tale, creator=None):
        return self._createAuxFolder(self, tale, DATADIRS_NAME, creator=creator)

    def createWorkspace(self, tale, creator=None):
        return self._createAuxFolder(self, tale, WORKSPACE_NAME, creator=creator)

    def _createAuxFolder(self, tale, rootFolderName, creator=None):
        if creator is None:
            creator = self.model('user').load(tale['creatorId'], force=True)

        if tale['public'] is not None and isinstance(tale['public'], bool):
            public = tale['public']
        else:
            public = False

        rootFolder = getOrCreateRootFolder(rootFolderName)
        auxFolder = self.model('folder').createFolder(
            rootFolder, str(tale['_id']), parentType='folder',
            public=public, reuseExisting=True)
        self.setUserAccess(
            auxFolder, user=creator, level=AccessType.ADMIN,
            save=True)
        auxFolder = self.model('folder').setMetadata(
            auxFolder, {'taleId': str(tale['_id'])})
        return auxFolder

    def updateTale(self, tale):
        """
        Updates a tale.

        :param tale: The tale document to update.
        :type tale: dict
        :returns: The tale document that was edited.
        """
        tale['updated'] = datetime.datetime.utcnow()
        return self.save(tale)

    def setAccessList(self, doc, access, save=False, user=None, force=False,
                      setPublic=None, publicFlags=None):
        """
        Overrides AccessControlledModel.setAccessList to encapsulate ACL
        functionality for a tale.

        :param doc: the tale to set access settings on
        :type doc: girder.models.tale
        :param access: The access control list
        :type access: dict
        :param save: Whether the changes should be saved to the database
        :type save: bool
        :param user: The current user
        :param force: Set this to True to set the flags regardless of the passed in
            user's permissions.
        :type force: bool
        :param setPublic: Pass this if you wish to set the public flag on the
            resources being updated.
        :type setPublic: bool or None
        :param publicFlags: Pass this if you wish to set the public flag list on
            resources being updated.
        :type publicFlags: flag identifier str, or list/set/tuple of them,
            or None
        """
        if setPublic is not None:
            self.setPublic(doc, setPublic, save=False)

        if publicFlags is not None:
            doc = self.setPublicFlags(doc, publicFlags, user=user, save=False,
                                      force=force)

        doc = AccessControlledModel.setAccessList(self, doc, access,
                                                  user=user, save=save, force=force)

        folder = AccessControlledModel.model('folder').load(
            doc['folderId'], user=user, level=AccessType.ADMIN)

        AccessControlledModel.model('folder').setAccessList(
            folder, access, user=user, save=save, force=force,
            setPublic=setPublic, publicFlags=publicFlags)

        image = AccessControlledModel.model('image', 'wholetale').load(
            doc['imageId'], user=user, level=AccessType.ADMIN)

        if image:
            AccessControlledModel.model('image', 'wholetale').setAccessList(
                image, access, user=user, save=save, force=force,
                setPublic=setPublic, publicFlags=publicFlags)

        return doc
