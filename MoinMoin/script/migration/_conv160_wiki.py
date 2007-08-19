# -*- coding: iso-8859-1 -*-
"""
    MoinMoin - convert content in 1.5.8 wiki markup to 1.6.0 style
               by using a modified 1.5.8 parser as translator.

    Assuming we have this "renames" map:
    -------------------------------------------------------
    'PAGE', 'some_page'        -> 'some page'
    'FILE', 'with%20blank.txt' -> 'with blank.txt'

    Markup transformations needed:
    -------------------------------------------------------
    ["some_page"]           -> [[some page]] # renamed
    [:some_page:some text]  -> [[some page|some text]]
    [:page:text]            -> [[page|text]]
                               (with a page not being renamed)

    attachment:with%20blank.txt -> [[attachment:with blank.txt]]
    attachment:some_page/with%20blank.txt -> [[attachment:some page/with blank.txt]]
    The attachment processing should also urllib.unquote the filename (or at
    least replace %20 by space) and put it into "quotes" if it contains spaces.

    @copyright: 2007 MoinMoin:JohannesBerg,
                2007 MoinMoin:ThomasWaldmann
    @license: GNU GPL, see COPYING for details.
"""

import re

from MoinMoin import i18n
i18n.wikiLanguages = lambda: {}

from MoinMoin import config, wikiutil, macro
from MoinMoin.action import AttachFile
from MoinMoin.Page import Page

from text_moin158_wiki import Parser

def convert_wiki(request, pagename, intext, renames):
    """ Convert content written in wiki markup """
    noeol = False
    if not intext.endswith('\r\n'):
        intext += '\r\n'
        noeol = True
    c = Converter(request, pagename, intext, renames)
    result = request.redirectedOutput(c.convert, request)
    if noeol and result.endswith('\r\n'):
        result = result[:-2]
    return result


class Converter(Parser):
    def __init__(self, request, pagename, raw, renames):
        self.pagename = pagename
        self.raw = raw
        self.renames = renames
        self.request = request
        self._ = None
        self.in_pre = 0

        self.formatting_rules = self.formatting_rules % {'macronames': u'|'.join(macro.getNames(self.request.cfg))}

    # no change

    def return_word(self, word):
        return word
    _emph_repl = return_word
    _emph_ibb_repl = return_word
    _emph_ibi_repl = return_word
    _emph_ib_or_bi_repl = return_word
    _u_repl = return_word
    _strike_repl = return_word
    _sup_repl = return_word
    _sub_repl = return_word
    _small_repl = return_word
    _big_repl = return_word
    _tt_repl = return_word
    _tt_bt_repl = return_word
    _remark_repl = return_word
    _table_repl = return_word
    _tableZ_repl = return_word
    _rule_repl = return_word
    _smiley_repl = return_word
    _smileyA_repl = return_word
    _ent_repl = return_word
    _ent_numeric_repl = return_word
    _ent_symbolic_repl = return_word
    _heading_repl = return_word
    _email_repl = return_word
    _notword_repl = return_word
    _indent_repl = return_word
    _li_none_repl = return_word
    _li_repl = return_word
    _ol_repl = return_word
    _dl_repl = return_word
    _comment_repl = return_word

    # translate pagenames using pagename translation map

    def _replace(self, key):
        """ replace a item_name if it is in the renames dict
            key is either a 2-tuple ('PAGE', pagename)
            or a 3-tuple ('FILE', pagename, filename)
        """
        current_page = self.pagename
        item_type, page_name, file_name = (key + (None, ))[:3]
        abs_page_name = wikiutil.AbsPageName(self.request, current_page, page_name)
        if item_type == 'PAGE':
            item_name = page_name
            key = (item_type, abs_page_name)
        elif item_type == 'FILE':
            item_name = file_name
            key = (item_type, abs_page_name, file_name)
        new_name = self.renames.get(key, item_name)
        if new_name != item_name and abs_page_name != page_name:
            pass # TODO we have to fix the (absolute) new_name to be a relative name (as it was before)
        return new_name

    def _replace_target(self, target):
        target_and_anchor = target.split('#', 1)
        if len(target_and_anchor) > 1:
            target, anchor = target_and_anchor
            target = self._replace(('PAGE', target))
            return '%s#%s' % (target, anchor)
        else:
            target = self._replace(('PAGE', target))
            return target

    # markup conversion

    def _macro_repl(self, word):
        # we use [[...]] for links now, macros will be <<...>>
        stripped_old = word[2:-2]
        decorated_new = "<<%s>>" % stripped_old
        # XXX later check whether some to be renamed pagename is used as macro param
        return decorated_new

    def _word_repl(self, word, text=None):
        """Handle WikiNames."""
        if not text:
            return word
        else: # internal use:
            return '[[%s|%s]]' % (word, text)

    def _wikiname_bracket_repl(self, word):
        """Handle special-char wikinames."""
        pagename = word[2:-2]
        if pagename:
            pagename = self._replace(('PAGE', pagename))
            return '[[%s]]' % pagename
        else:
            return word

    def _interwiki_repl(self, word):
        """Handle InterWiki links."""
        wikitag, wikiurl, wikitail, wikitag_bad = wikiutil.resolve_wiki(self.request, word)
        if wikitag_bad:
            return word
        else:
            wikiname, pagename = word.split(':', 1)
            pagename = wikiutil.url_unquote(pagename) # maybe someone has used %20 for blanks in pagename
            camelcase = wikiutil.isStrictWikiname(pagename)
            if wikiname in ('Self', self.request.cfg.interwikiname):
                pagename = self._replace(('PAGE', pagename))
                if camelcase:
                    return '%s' % pagename # optimize special case
                else:
                    return '[[%s]]' % pagename # optimize special case
            else:
                if ' ' in pagename: # we could get a ' '  by urlunquoting
                    return '[[%s:%s]]' % (wikiname, pagename)
                else:
                    return '%s:%s' % (wikiname, pagename)

    def interwiki(self, url_and_text):
        if len(url_and_text) == 1:
            url = url_and_text[0]
            text = ''
        else:
            url, text = url_and_text
            text = '|' + text

        # keep track of whether this is a self-reference, so links
        # are always shown even the page doesn't exist.
        scheme, url = url.split(':', 1)
        wikiname, pagename = wikiutil.split_wiki(url)
        if (url.startswith(wikiutil.CHILD_PREFIX) or # fancy link to subpage [wiki:/SubPage text]
            wikiname in ('Self', self.request.cfg.interwikiname, '') or # [wiki:Self:LocalPage text] or [:LocalPage:text]
            Page(self.request, url).exists()): # fancy link to local page [wiki:LocalPage text]
            pagename = wikiutil.url_unquote(pagename)
            pagename = self._replace_target(pagename)
            return '[[%s%s]]' % (pagename, text)

        wikitag, wikiurl, wikitail, wikitag_bad = wikiutil.resolve_wiki(self.request, url)
        wikitail = wikiutil.url_unquote(wikitail)

        # link to self?
        if wikitag is None:
            if wikiutil.isPicture(wikitail):
                return '{{%s%s}}' % (wikitail, text)
            else:
                return '[[%s%s]]' % (wikitail, text)
        else:
            if wikiutil.isPicture(wikitail):
                return '{{%s:%s%s}}' % (wikitag, wikitail, text)
            else:
                return '[[%s:%s%s]]' % (wikitag, wikitail, text)

    def attachment(self, url_and_text):
        """ This gets called on attachment URLs. """
        if len(url_and_text) == 1:
            url = url_and_text[0]
            text = ''
        else:
            url, text = url_and_text
            text = '|' + text

        scheme, fname = url.split(":", 1)
        #scheme, fname, text = wikiutil.split_wiki(target_and_text)

        pagename, fname = AttachFile.absoluteName(fname, self.pagename)
        from_this_page = pagename == self.pagename
        fname = self._replace(('FILE', pagename, fname))
        fname = wikiutil.url_unquote(fname, want_unicode=True)
        fname = self._replace(('FILE', pagename, fname))
        pagename = self._replace(('PAGE', pagename))
        if from_this_page:
            name = fname
        else:
            name = "%s/%s" % (pagename, fname)

        if scheme == 'drawing':
            return "{{drawing:%s%s}}" % (name, text)

        # check for image URL, and possibly return IMG tag
        # (images are always inlined, just like for other URLs)
        if wikiutil.isPicture(name):
            if not text:
                text = name.split('/')[-1]
                text = ''.join(text.split('.')[:-1])
                text = wikiutil.url_unquote(text) # maybe someone has used %20 for blanks
                text = '|' + text
            return "{{attachment:%s%s}}" % (name, text)

        # inline the attachment
        if scheme == 'inline':
            return '{{attachment:%s%s}}' % (name, text)
        else: # 'attachment'
            return '[[attachment:%s%s]]' % (name, text)

    def _url_repl(self, word):
        """Handle literal URLs including inline images."""
        scheme = word.split(":", 1)[0]

        if scheme == 'wiki':
            return self.interwiki([word])
        if scheme in self.attachment_schemas:
            return '%s' % self.attachment([word])

        if wikiutil.isPicture(word): # magic will go away in 1.6!
            name = word.split('/')[-1]
            name = ''.join(name.split('.')[:-1])
            name = wikiutil.url_unquote(name) # maybe someone has used %20 for blanks
            return '{{%s|%s}}' % (word, name) # new markup for inline images
        else:
            return word

    def _url_bracket_repl(self, word):
        """Handle bracketed URLs."""
        word = word[1:-1] # strip brackets

        # Local extended link?
        if word[0] == ':':
            words = word[1:].split(':', 1)
            link, text = (words + ['', ''])[:2]
            if link.strip() == text.strip():
                text = ''
            link = self._replace_target(link)
            if text:
                text = '|' + text
            return '[[%s%s]]' % (link, text)

        # Traditional split on space
        words = word.split(None, 1)
        if words[0][0] == '#':
            # anchor link
            link, text = (words + ['', ''])[:2]
            if link.strip() == text.strip():
                text = ''
            #link = self._replace_target(link)
            if text:
                text = '|' + text
            return '[[%s%s]]' % (link, text)

        scheme = words[0].split(":", 1)[0]
        if scheme == "wiki":
            return self.interwiki(words)
            #scheme, wikiname, pagename, text = self.interwiki(word)
            #print "%r %r %r %r" % (scheme, wikiname, pagename, text)
            #if wikiname in ('Self', self.request.cfg.interwikiname, ''):
            #    if text:
            #        text = '|' + text
            #    return '[[%s%s]]' % (pagename, text)
            #else:
            #    if text:
            #        text = '|' + text
            #    return "[[%s:%s%s]]" % (wikiname, pagename, text)
        if scheme in self.attachment_schemas:
            return '%s' % self.attachment(words)

        target, desc = (words + ['', ''])[:2]
        if wikiutil.isPicture(desc) and re.match(self.url_rule, desc):
            #return '[[%s|{{%s|%s}}]]' % (words[0], words[1], words[0])
            return '[[%s|{{%s}}]]' % (target, desc)
        else:
            if desc:
                desc = '|' + desc
            return '[[%s%s]]' % (target, desc)

    def _pre_repl(self, word):
        w = word.strip()
        if w == '{{{' and not self.in_pre:
            self.in_pre = True
        elif w == '}}}' and self.in_pre:
            self.in_pre = False
        return word

    def _processor_repl(self, word):
        self.in_pre = True
        return word

    def scan(self, scan_re, line):
        """ Scans one line - append text before match, invoke replace() with match, and add text after match.  """
        result = []
        lastpos = 0

        for match in scan_re.finditer(line):
            # Add text before the match
            if lastpos < match.start():
                result.append(line[lastpos:match.start()])
            # Replace match with markup
            result.append(self.replace(match))
            lastpos = match.end()

        # Add remainder of the line
        result.append(line[lastpos:])
        return u''.join(result)


    def replace(self, match):
        """ Replace match using type name """
        result = []
        for _type, hit in match.groupdict().items():
            if hit is not None and not _type in ["hmarker", ]:
                # Get replace method and replace hit
                replace = getattr(self, '_' + _type + '_repl')
                # print _type, hit
                result.append(replace(hit))
                return ''.join(result)
        else:
            # We should never get here
            import pprint
            raise Exception("Can't handle match %r\n%s\n%s" % (
                match,
                pprint.pformat(match.groupdict()),
                pprint.pformat(match.groups()),
            ))

        return ""

    def convert(self, request):
        """ For each line, scan through looking for magic
            strings, outputting verbatim any intervening text.
        """
        self.request = request
        # prepare regex patterns
        rules = self.formatting_rules.replace('\n', '|')
        if self.request.cfg.bang_meta:
            rules = ur'(?P<notword>!%(word_rule)s)|%(rules)s' % {
                'word_rule': self.word_rule,
                'rules': rules,
            }
        #pre_rules = self.pre_formatting_rules.replace('\n', '|')
        #pre_scan_re = re.compile(pre_rules, re.UNICODE)
        scan_re = re.compile(rules, re.UNICODE)
        eol_re = re.compile(r'\r?\n', re.UNICODE)

        rawtext = self.raw

        # remove last item because it's guaranteed to be empty
        self.lines = eol_re.split(rawtext)[:-1]
        self.in_processing_instructions = True

        # Main loop
        for line in self.lines:
            # ignore processing instructions
            if self.in_processing_instructions:
                found = False
                for pi in ("##", "#format", "#refresh", "#redirect", "#deprecated",
                           "#pragma", "#form", "#acl", "#language"):
                    if line.lower().startswith(pi):
                        self.request.write(line + '\r\n')
                        found = True
                        break
                if not found:
                    self.in_processing_instructions = False
                else:
                    continue # do not parse this line
            if not line.strip():
                self.request.write(line + '\r\n')
            else:
                # Scan line, format and write
                scanning_re = self.in_pre and pre_scan_re or scan_re
                formatted_line = self.scan(scanning_re, line)
                self.request.write(formatted_line + '\r\n')

