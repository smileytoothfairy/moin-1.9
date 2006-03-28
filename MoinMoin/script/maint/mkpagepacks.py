# -*- coding: iso-8859-1 -*-
"""
    MoinMoin - Package Generator

    @copyright: 2005 by Alexander Schremmer,
                2006 by MoinMoin:ThomasWaldmann
    @license: GNU GPL, see COPYING for details.
"""

import os
import zipfile
from sets import Set
from datetime import datetime

from MoinMoin import wikidicts, wikiutil
from MoinMoin.Page import Page
from MoinMoin.PageEditor import PageEditor
from MoinMoin.packages import packLine, unpackLine, MOIN_PACKAGE_FILE
from MoinMoin.script._util import MoinScript

EXTRA = u'extra'
NODIST = u'nodist'
ALL = u'all_languages'
COMPRESSION_LEVEL = zipfile.ZIP_STORED

class PluginScript(MoinScript):
    def __init__(self, argv, def_values):
        MoinScript.__init__(self, argv, def_values)

    def buildPageSets(self):
        """ Calculates which pages should go into which package. """
        request = self.request
        pageSets = {}

        allPages = Set(request.rootpage.getPageList())

        systemPages = wikidicts.Group(request, "SystemPagesGroup").members()

        for pagename in systemPages:
            if pagename.endswith("Group"):
                #print x + " -> " + repr(wikidicts.Group(request, x).members())
                self.gd.addgroup(request, pagename)

        langPages = Set()
        for name, group in self.gd.dictdict.items():
            group.expandgroups(self.gd)
            groupPages = Set(group.members() + [name])
            name = name.replace("SystemPagesIn", "").replace("Group", "")
            pageSets[name] = groupPages
            langPages |= groupPages

        specialPages = Set(["SystemPagesGroup"])

        masterNonSystemPages = allPages - langPages - specialPages

        moinI18nPages = Set([x for x in masterNonSystemPages if x.startswith("MoinI18n")])
        
        nodistPages = moinI18nPages | Set(["InterWikiMap", ])

        extraPages = masterNonSystemPages - nodistPages

        pageSets[ALL] = langPages
        
        for name in pageSets.keys():
            if name not in (u"English"):
                pageSets[name] -= pageSets[u"English"]
                pageSets[name] -= nodistPages

        pageSets[EXTRA] = extraPages   # stuff that maybe should be in some language group
        pageSets[NODIST] = nodistPages # we dont want to have them in dist archive
        return pageSets

    def packagePages(self, pagelist, filename, function):
        """ Puts pages from pagelist into filename and calls function on them on installation. """
        request = self.request
        try:
            os.remove(filename)
        except OSError:
            pass
        zf = zipfile.ZipFile(filename, "w", COMPRESSION_LEVEL)

        cnt = 0
        script = [packLine(['MoinMoinPackage', '1']), ]
                  
        for pagename in pagelist:
            pagename = pagename.strip()
            page = Page(request, pagename)
            if page.exists():
                cnt += 1
                script.append(packLine([function, str(cnt), pagename]))
                timestamp = wikiutil.version2timestamp(page.mtime_usecs())
                zi = zipfile.ZipInfo(filename=str(cnt), date_time=datetime.fromtimestamp(timestamp).timetuple()[:6])
                zi.compress_type = COMPRESSION_LEVEL
                zf.writestr(zi, page.get_raw_body().encode("utf-8"))
            else:
                #import sys
                #print >>sys.stderr, "Could not find the page %s." % pagename.encode("utf-8")
                pass

        script += [packLine(['Print', 'Installed MoinMaster page bundle %s.' % os.path.basename(filename)])]

        zf.writestr(MOIN_PACKAGE_FILE, u"\n".join(script).encode("utf-8"))
        zf.close()

    def removePages(self, pagelist):
        """ Pages from pagelist get removed from the underlay directory. """
        request = self.request
        import shutil
        for pagename in pagelist:
            pagename = pagename.strip()
            page = Page(request, pagename)
            try:
                underlay, path = page.getPageBasePath(-1)
                shutil.rmtree(path)
            except:
                pass

    def packageCompoundInstaller(self, bundledict, filename):
        """ Creates a package which installs all other packages. """
        try:
            os.remove(filename)
        except OSError:
            pass
        zf = zipfile.ZipFile(filename, "w", COMPRESSION_LEVEL)

        script = [packLine(['MoinMoinPackage', '1']), ]

        script += [packLine(["InstallPackage", "SystemPagesSetup", name + ".zip"])
                   for name in bundledict.keys() if name not in (NODIST, EXTRA, ALL, u"English")]
        script += [packLine(['Print', 'Installed all MoinMaster page bundles.'])]

        zf.writestr(MOIN_PACKAGE_FILE, u"\n".join(script).encode("utf-8"))
        zf.close()

    def mainloop(self):
        # self.options.wiki_url = 'localhost/'
        if self.options.wiki_url and '.' in self.options.wiki_url:
            print "NEVER EVER RUN THIS ON A REAL WIKI!!! This must be run on a local testwiki."
            return
        if self.options.config_dir:
            print "NEVER EVER RUN THIS ON A REAL WIKI!!! This must be run on a local testwiki without any --config-dir!"
            return
            
        self.init_request() # this request will work on a test wiki in testwiki/ directory
                            # we assume that there are current moinmaster pages there
        request = self.request
        request.form = request.args = request.setup_args()

        if not ('testwiki' in request.cfg.data_dir and 'testwiki' in request.cfg.data_underlay_dir):
            print "NEVER EVER RUN THIS ON A REAL WIKI!!! This must be run on a local testwiki."
            return
            
        self.gd = wikidicts.GroupDict(request)
        self.gd.reset()

        print "Building page sets ..."
        pageSets = self.buildPageSets()

        print "Creating packages ..."
        generate_filename = lambda name: os.path.join('testwiki', 'underlay', 'pages', 'SystemPagesSetup', 'attachments', '%s.zip' % name)

        self.packageCompoundInstaller(pageSets, generate_filename(ALL))

        [self.packagePages(list(pages), generate_filename(name), "ReplaceUnderlay") 
            for name, pages in pageSets.items() if not name in (u'English', ALL, NODIST)]

        [self.removePages(list(pages)) 
            for name, pages in pageSets.items() if not name in (u'English', ALL)]

        print "Finished."
