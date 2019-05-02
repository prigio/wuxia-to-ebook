#!/usr/bin/env python3
# -*- encoding: utf-8 -*-

import os
import base64
import time
import subprocess
from subprocess import CalledProcessError

import requests
from requests_html import HTMLSession, HTML

## Configuration
novel = "the-great-ruler"

USE_CACHE = True
REPROCESS_CACHED_HTML = True
SPLIT = 100 # split a big ebook in groups of <SPLIT> chapters, thus generating multiple EPUB files. Set to None if only one book is desired
WUXIA_URL = "https://www.wuxiaworld.com"

###
NOVEL_FOLDER = novel
# folder where the cache is stored
CACHE_FOLDER = os.path.join(NOVEL_FOLDER, "CACHE")
# filename of the markdown file generating the epub
output_md = os.path.join(NOVEL_FOLDER, "%s.md" % novel)
# filename of the epub
output_epub = os.path.join(NOVEL_FOLDER, "%s.epub" % novel)
# filename of the epub in case splitting is used. it MUST contain two additional variables for the starting and ending chapter.
output_epub_split = os.path.join(NOVEL_FOLDER, "%s_%%s-%%s.epub" % novel)

###
###
###

def get_chapter_markdown(html_element):
	# get the title
	try: 
		title = html_element.find("div.section div.section-content div.panel div.caption h4")[0].text
	except:
		title=""
		print('Title not found for url="%s"' % l)
	# get all the paragraphs	
	#paragraphs = [p.text.replace("…","...") for p in html_element.find("div.section div.section-content div.p-15 div.fr-view p") if p.text != "" and not p.text.startswith("Previous")]
	paragraphs = [p.raw_html.decode(html_element.encoding).replace("…","...") for p in html_element.find("div.section div.section-content div.p-15 div.fr-view p") if p.text != "" and not p.text.startswith("Previous")]
	# the first might be similar to the title, therefore it gets excluded
	if paragraphs[0][0:5] == title[0:5]:
		paragraphs = paragraphs[1:]

	# concatenate all the paragraphs
	text = "\n\n".join(paragraphs)
	# generate markdown for this chapter
	chapter_markdown = "# %s\n\n%s\n\n"% (title, text)
	return chapter_markdown

def generate_epub(markdown_file, epub_file):
	start_time = time.time()
	try:
		cmdline = ["pandoc", "--toc", "--to=epub", "--from=markdown", "--output=%s" % epub_file, markdown_file]
		#https://docs.python.org/2/library/subprocess.html
		pandoc_output = subprocess.check_output(cmdline, stderr=subprocess.STDOUT)
	except CalledProcessError as e:
		retval = e.returncode
		pandoc_output = e.output.decode('utf8').splitlines()
		if len(pandoc_output)>=20:
			pandoc_output = pandoc_output[-20:]
		print("Pandoc terminated with ERROR.\n...\n%s" % "\n".join(pandoc_output))
		return False
	else:
		print("Epub generation successful into file=%s, took %s seconds" % (epub_file, round(time.time() - start_time,3)))
		return True

##
##
##

overall_start_time = time.time()
start_time = time.time()
print("Generating epub for novel %s" % novel)

if USE_CACHE: print("- Using cached HTML files if present")
else: print("- NOT using cached HTML files")

if REPROCESS_CACHED_HTML: print("- Reprocessing cached HTML files, if present")
else: print("- Using cached markdown files, if present")


print("Getting info about novel from Wuxiaworld")
session = HTMLSession()
r = session.get("%s/novel/%s" % (WUXIA_URL, novel))
#get all elements referring to chapters

# a.links is a set of links present within the element
links_elements = ["%s%s" % (WUXIA_URL, a.links.pop()) for a in r.html.find("li.chapter-item a")]

# sort the chapters by number, just in case
#links_elements.sort()

book_markdown_template = """---
title: %(title)s
subtitle: %(subtitle)s
...

""" 

print("Found %s chapters" % len(links_elements))

if not os.path.isdir(novel):
	print('Creating folder="%s"' % novel)
	os.mkdir(novel)

if USE_CACHE and not os.path.isdir(CACHE_FOLDER):
	print('Creating cache folder="%s"' % CACHE_FOLDER)
	os.mkdir(CACHE_FOLDER)


i = 0
chapter_markdowns = []	
for l in links_elements:
	chapter_markdown = None
	i += 1
	if i%100 == 0:
		print("Processed %s chapters" % i)

	chapterfilename = base64.b64encode(bytes(l, encoding="utf-8")).decode("utf-8")
	chapterfile_html =  os.path.join(
						CACHE_FOLDER,
						"%s.html" % chapterfilename
					)
	chapterfile_md = os.path.join(
						CACHE_FOLDER,
						"%s.md" % chapterfilename
					)
	if USE_CACHE and not REPROCESS_CACHED_HTML and os.path.isfile(chapterfile_md):
		# read Markdown from cached file
		with open(chapterfile_md, "r") as f:
			chapter_markdown = f.read()
	elif USE_CACHE and os.path.isfile(chapterfile_html):
		# read HTML contents from cache file
		with open(chapterfile_html, "rb") as f:
			html = HTML(html=f.read())
	else:
		# get HTML content from website
		html = session.get(l).html
		if USE_CACHE:
			# store HTML contents within a cache file
			with open(chapterfile_html, "wb") as f:
				f.write(html.raw_html)		

	if chapter_markdown == None:
		# Need to process the HTML contents into markdown
		chapter_markdown = get_chapter_markdown(html)
		
		if USE_CACHE:
			# store generated markdown in a cache file
			with open(chapterfile_md, "w") as f:
				f.write(chapter_markdown)		

	chapter_markdowns.append(chapter_markdown)

print("Processing %s chapters, took %s seconds" % (len(chapter_markdowns), round(time.time() - start_time, 3)))

if not SPLIT:
	print('Generating markdown file')	
	book_markdown = book_markdown_template % {
		'title': novel, 
		'subtitle': "Chapters 1-%s" % len(chapter_markdowns)}
	book_markdown = book_markdown + "\n".join(chapter_markdowns)
	
	with open(output_md, "w") as f:
		f.write(book_markdown)
	
	print('Markdown generation successful into file="%s", took %s seconds' % (output_md, round(time.time() - start_time,3)))
	print('Generating epub file')
	generate_epub(markdown_file=output_md, epub_file=output_epub)
else:
	split_markdowns = [chapter_markdowns[i:i + SPLIT] for i in range(0, len(chapter_markdowns), SPLIT)]
	count_output_chapters = 0
	for group in split_markdowns:
		start_time = time.time()
		chpt_from = count_output_chapters + 1
		chpt_to = count_output_chapters + len(group)
		book_markdown = book_markdown_template % {
			'title': "%s [%s-%s]" % (novel, chpt_from, chpt_to), 
			'subtitle': "Chapters %s - %s" % (chpt_from, chpt_to)
			}
		
		book_markdown = book_markdown + "\n".join(group)

		with open(output_md, "w") as f:
			f.write(book_markdown)
		
		print('Markdown generation for chapters %s-%s successful into file="%s", took %s seconds' % (chpt_from, chpt_to, output_md, round(time.time() - start_time,3)))
		#print('Generating epub file')
		generate_epub(markdown_file=output_md, 
			epub_file=output_epub_split % (chpt_from, chpt_to))

		count_output_chapters += len(group)

print("Done, took %s seconds" % round(time.time() - overall_start_time, 3))
