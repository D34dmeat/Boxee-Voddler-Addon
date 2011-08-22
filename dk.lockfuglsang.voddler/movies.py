# Main .py file
# TODOs
# * Localization - all strings in something else :D
# * Add to voddler playlist + favourite
# * Play trailer
import string, math
import mc
from mc import *
import time

from pprint import pprint

import login
from status import *
import voddlerapi

# IDs
WINDOW_ID=14000
POPUP_ID=14015 # redefined here, just to not import the popup... circular ref.
USERNAME_LBL_ID=102
PAGETYPE_LBL_ID=111

MOVIES_ID=200

GENRE_ID=201
SORTING_ID=202
CATEGORY_ID=203
PAGE_LABEL=110
STATUS_LABEL=120
TRAILER_WINDOW=14025

# Constants
pageSize=100
TIME_BETWEEN_SEARCHES = 3 # at least 3 seconds between searches - makes sure that we don't accidentially skip pages

# Global vars
multiPageCache = {}
pageCache = {}
currentMovieIndex = 1
currentPage = 0
lastPage = 0
maxPage = 0
maxCount = 0
lastSearch = 0

oldPageType = None
pageType = 'movie'

# -----------------------------------------------------------------------------
# Actions
# -----------------------------------------------------------------------------
def playMovie(listId=MOVIES_ID):
    movieList = GetActiveWindow().GetList(listId)
    index = movieList.GetFocusedItem()
    movie = movieList.GetItem(index)

    ShowDialogWait()
    try:
        status("Playing movie %s" % movie.GetLabel())
        player = mc.GetApp().GetLocalConfig().GetValue('player')
        url = voddlerapi.getAPI().getMovieURL(movie.GetProperty('id'), player)
        if not url:
            # revert to web-url
            url = movie.GetProperty('url')
        print "Playing %s" % url
        movie.SetPath(url)
    finally:
        hideWaitDialog()
    mc.GetPlayer().PlayWithActionMenu(movie)

def showPopup():
    mc.ActivateWindow(POPUP_ID)

def removeFromPlaylist(list='favorites'):
    movieList = mc.GetActiveWindow().GetList(MOVIES_ID)
    index = movieList.GetFocusedItem()
    movie = movieList.GetItem(index)
    voddlerapi.getAPI().removeFromPlaylist(movie.GetProperty('id'), list)
    movie.SetProperty('is%s' % string.capitalize(list), 'false')
    # Apparently this doesn't go into the cache :(
    global pageCache, currentPage
    del pageCache[currentPage]

def addToPlaylist(list='favorites'):
    movieList = mc.GetActiveWindow().GetList(MOVIES_ID)
    index = movieList.GetFocusedItem()
    movie = movieList.GetItem(index)
    voddlerapi.getAPI().addToPlaylist(movie.GetProperty('id'), list)
    movie.SetProperty('is%s' % string.capitalize(list), 'true')
    # Apparently this doesn't go into the cache :(
    global pageCache, currentPage
    del pageCache[currentPage]

def search(reset=False):
    global maxPage, maxCount, currentPage, pageCache, lastPage, lastSearch, pageType
    api = voddlerapi.getAPI()
    ShowDialogWait()
    status("Searching...")
    saveUserSettings()
    window = GetWindow(WINDOW_ID)
    mainList = window.GetList(MOVIES_ID)
    statusLabel = window.GetLabel(STATUS_LABEL)
    statusLabel.SetVisible(False)
    if reset:
        currentPage = 0
        pageCache.clear()
        lastPage = 0
    try:
        g = getGenre()
        s = getSorting()
        c = getCategory()
        offset = currentPage * pageSize
        items = ListItems()
        if currentPage in pageCache.keys():
            items = pageCache[currentPage]
        else:
            status("Fetching page %i" % (currentPage+1))
            maxCount, data = api.search(pageType, c, g, s, offset, pageSize)
            maxPage = (maxCount-1) / pageSize
            if maxPage < 0:
                maxPage = 0
            itemsOnCurrentPage = min(pageSize, maxCount, maxCount - (currentPage*pageSize))
            for index, movie in enumerate(data):
                status("Generating page %i of %i" % (currentPage+1, maxPage+1), index+1, itemsOnCurrentPage)
                item = ListItem(ListItem.MEDIA_VIDEO_FEATURE_FILM)
                movie.showOnListItem(item, offset+index)
                items.append(item)
            pageCache[currentPage] = items

        mainList.SetItems(items)
        updateStatusLabel()
    finally:
        hideWaitDialog()
        if mainList.IsVisible():
            mainList.SetFocus()
        lastPage = currentPage
        lastSearch = time.time()
    if maxCount == 0:
        mc.ShowDialogNotification("No movies matched the filters!")

def updateStatusLabel():
    global maxCount, currentPage, maxPage
    window = mc.GetActiveWindow()
    statusLabel = window.GetLabel(STATUS_LABEL)
    mainList = window.GetList(MOVIES_ID)
    if maxCount == 0:
        statusLabel.SetLabel("no movies found")
        mainList.SetVisible(False)
    else:
        statusLabel.SetLabel("Found %i movies" % maxCount)
        mainList.SetVisible(True)
    statusLabel.SetVisible(True)
    window.GetLabel(PAGE_LABEL).SetLabel("Page %i of %i" % (currentPage+1, maxPage+1))

''' Makes sure that we don't accidentially spawn multiple searches due to
    erradic navigation.
'''
def isSearchAllowed():
    global lastSearch
    return time.time() - lastSearch > TIME_BETWEEN_SEARCHES

def nextPage():
    global currentPage, maxPage
    if not isSearchAllowed():
        return
    if currentPage < maxPage:
        currentPage += 1
        search()
    else:
        currentPage = 0
        search()
    GetWindow(WINDOW_ID).GetList(MOVIES_ID).SetFocusedItem(0)

def prevPage():
    global currentPage, maxPage
    if not isSearchAllowed():
        return
    if currentPage > 0:
        currentPage -= 1
        search()
    else:
        currentPage = maxPage
        search()
    list = GetWindow(WINDOW_ID).GetList(MOVIES_ID)
    list.SetFocusedItem(len(list.GetItems())-1)

# -----------------------------------------------------------------------------
# Populate Controls
# -----------------------------------------------------------------------------
''' Changes the default sorting of genres to be All > Name
'''
def _getGenreKey(g):
    if g.GetProperty('value') == 'all':
        return '000 All'
    return g.GetLabel()

def populateGenre():
    global pageType
    genres = voddlerapi.getAPI().getGenres(pageType)
    #pprint(data)
    items = mc.ListItems()
    itemList = []
    # dicts are not that easily sorted...
    for value, name in genres.items():
        #pprint(g)
        item = ListItem(ListItem.MEDIA_UNKNOWN)
        item.SetLabel(name)
        item.SetProperty('value', value)
        itemList.append(item)
    # ... so we wait, and then sort
    for item in sorted(itemList, key=_getGenreKey):
        items.append(item)
    genre = mc.GetActiveWindow().GetList(GENRE_ID)
    genre.SetItems(items)

def populateSorting():
    items = mc.ListItems()
    data = [{'name' : 'Rating', 'value' : 'rating'}, {'name' : 'Views', 'value' : 'views'}, {'name' : 'Alphabetical', 'value' : 'alphabetical'}]
    for g in data:
        key, label = g['value'], g['name']
        item = ListItem(ListItem.MEDIA_UNKNOWN)
        item.SetLabel(label)
        item.SetProperty('value', key)
        item.SetIcon("sort_%s_on.png" % key)
        item.SetThumbnail("sort_%s.png" % key)
        items.append(item)
    mc.GetActiveWindow().GetList(SORTING_ID).SetItems(items)

def populateCategory():
    items = mc.ListItems()
    data = [{'name' : 'Free', 'value' : 'free'}, {'name' : 'Rent', 'value' : 'premium'}, {'name' : 'All', 'value' : 'all'}]
    for g in data:
        if g['name']:
            item = ListItem(ListItem.MEDIA_UNKNOWN)
            item.SetLabel(g['name'])
            item.SetProperty('value', g['value'])
            items.append(item)
    mc.GetActiveWindow().GetList(CATEGORY_ID).SetItems(items)

def populateLists():
    window = GetWindow(WINDOW_ID)
    list = window.GetList(MOVIES_ID)
    items = ListItems()
    item = ListItem(ListItem.MEDIA_VIDEO_FEATURE_FILM)
    items.append(item)
    list.SetItems(items)

def populateControls():
    # Initialize UI
    ShowDialogWait()
    try:
        window = GetActiveWindow()
        if login.getLoggedIn():
            window.GetLabel(USERNAME_LBL_ID).SetLabel(login.getLoggedIn())
        populateSorting()
        populateCategory()
        populateGenre()
        restoreUserSettings()
    finally:
        hideWaitDialog()

# -----------------------------------------------------------------------------
# User Settings
# -----------------------------------------------------------------------------
listFields = {'genre' : 201, 'sorting' : 202, 'type' : 203}
def restoreUserSettings():
    global pageSize, pageType
    print "restoring user-settings"
    window = GetWindow(WINDOW_ID)
    config = GetApp().GetLocalConfig()

    numPages = config.GetValue('%s/pages' % pageType)
    if numPages:
        pageSize = int(numPages)
    for key, id in listFields.items():
        value = config.GetValue("%s/%s" % (pageType, key))
        print "restoring %s as %s" % (key, value)
        if value:
            list = window.GetList(id)
            for index, item in enumerate(list.GetItems()):
                if item.GetProperty('value') == value:
                    list.SetFocusedItem(index)
                    break
        window.GetList(id).SetVisible(True)

def saveUserSettings():
    global pageType
    print "saving user-settings"
    window = GetWindow(WINDOW_ID)
    config = GetApp().GetLocalConfig()
    for key, id in listFields.items():
        list = window.GetList(id)
        index = list.GetFocusedItem()
        value = list.GetItem(index).GetProperty('value')
        config.SetValue("%s/%s" % (pageType, key), "%s" % value)

# -----------------------------------------------------------------------------
# Helper / Library Methods
# -----------------------------------------------------------------------------
def _getListItemValue(listId):
    list = GetActiveWindow().GetList(listId)
    focusIndex = list.GetFocusedItem()
    focusItem = list.GetItem(focusIndex)
    return focusItem.GetProperty('value')

def getGenre():
    return _getListItemValue(GENRE_ID)

def getSorting():
    return _getListItemValue(SORTING_ID)

def getCategory():
    return _getListItemValue(CATEGORY_ID)

def loadPage():
    global pageCache, currentPage, maxPage, pageType, oldPageType, multiPageCache
    window = mc.GetActiveWindow()
    window.GetControl(1).SetVisible(False)
    mc.ShowDialogWait()
    pageType = mc.GetApp().GetLocalConfig().GetValue('pageType')
    if not pageType:
        pageType = 'movie'
    if not pageType in multiPageCache.keys():
        multiPageCache[pageType] = {}
    pageCache = multiPageCache[pageType]
    pagetypes = {'movie' : 'Movies', 'episode' : 'TVSeries', 'documentary' : 'Documentaries'}
    window.GetLabel(PAGETYPE_LBL_ID).SetLabel(pagetypes[pageType])
    populateControls()
    restoreUserSettings()
    if not pageCache:
        populateLists()
        search(True)
    else:
        window.GetList(MOVIES_ID).SetItems(pageCache[currentPage])
        # restore dynamic labels
        updateStatusLabel()
    oldPageType = pageType
    hideWaitDialog()
    window.GetControl(1).SetVisible(True)
    if maxCount > 0:
        window.GetList(MOVIES_ID).SetFocus()
    else:
        window.GetList(GENRE_ID).SetFocus()

if __name__ == '__main__':
    # Show the main window
    mc.ActivateWindow(WINDOW_ID)
