#!/usr/bin/env python3
# -*- encoding: utf-8 -*-

"""
Generates EPUB files of novels on WuxiaWorld.com
REQUIRES the "pandoc" application being installed and available within the PATH

"""
import os
import sys
import base64
import time
import argparse
import subprocess
from subprocess import CalledProcessError

# these libraries require being installed
import requests
from requests_html import HTMLSession, HTML


def process_front_matter(novel_url, novel, novel_folder=None):
	print("Getting info about novel from Wuxiaworld")
	session = HTMLSession()
	r = session.get(novel_url)

	if not r.ok:
		raise ValueError('URL="%s" could not be downloaded: %s - %s' % (novel_url, r.status_code, r.reason))

	novel_folder = novel if not novel_folder else novel_folder
	
	if not os.path.isdir(novel_folder):
		print('  Creating novel folder="%s"' % novel_folder)
		os.mkdir(novel_folder)
	
	try: 
		novel_title = r.html.find("div.section-content div.p-15 h4")[0].text
		print("  Title: %s" % novel_title)
	except: 
		print("  WARN: could not identify novel title")
		novel_title = novel
	try: 
		novel_info = r.html.find("div.section-content div.p-15 div.media div.fr-view")[0].text
		novel_info = novel_info.replace("\n", "; ")
	except: 
		print("  WARN: could not identify novel information")
		novel_info = ""
	try:
		novel_image_url = img = r.html.find("div.section-content div.p-15 div.media img")[0].attrs['src']
		image_r = session.get(novel_image_url)
		if image_r.headers['Content-Type'] == "image/jpeg":
			image_file = "%s.jpg" % novel
		elif image_r.headers['Content-Type'] == "image/png":
			image_file = "%s.png" % novel
		else:
			image_file = "%s.img" % novel

		image_file = os.path.join(novel_folder, image_file)
		if not os.path.isfile(image_file):
			with open(image_file, "wb") as f:
				f.write(image_r.content)
			print('  Saved novel image file="%s"' % image_file)
	except:
		print("  WARN: could not identify novel image")	
		image_file = None

	#get all elements referring to chapters
	# a.links is a set of links present within the element
	chapter_urls = [a.absolute_links.pop() for a in r.html.find("li.chapter-item a")]
	print("  Found %s chapters" % len(chapter_urls))

	session.close()
	# The keys returned should be valid metadata for pandoc's EPUB. See https://pandoc.org/MANUAL.html#epub-metadata
	# Only string and integer values will be transformed into metadata, any other format, e.g. lists will be discarded
	return {'pagetitle': novel_title, 'title': novel_title, 'description': novel_info, 'cover-image': image_file, 'chapter_urls': chapter_urls, 'date': time.strftime("%Y-%m-%d")}


def process_chapters(chapter_urls, novel_folder, use_cache=True, reprocess_cached_html=False, cache_folder="CACHE"):
	
	chapter_markdowns = []
	start_time = time.time()
	print("Processing chapters")
	# folder where the cache is stored
	cache_folder = os.path.join(novel_folder, cache_folder)
	if not os.path.isdir(novel_folder):
		print('  Creating novel folder="%s"' % novel_folder)
		os.mkdir(novel_folder)
	if use_cache and not os.path.isdir(cache_folder):	
		print('  Creating cache folder="%s"' % cache_folder)
		os.mkdir(cache_folder)	

	i = 0
	session = HTMLSession()
	for l in chapter_urls:
		chapter_markdown = None
		i += 1
		if i%100 == 0:
			print("   ... %s chapters" % i)
		# chapterfilename = base64.b64encode(bytes(l, encoding="utf-8")).decode("utf-8")
		chapterfilename = "Chapter-%04d" % i
		chapterfile_html =  os.path.join(
							cache_folder,
							"%s.html" % chapterfilename
						)
		chapterfile_md = os.path.join(
							cache_folder,
							"%s.md" % chapterfilename
						)
		if use_cache and not reprocess_cached_html and os.path.isfile(chapterfile_md):
			# read Markdown from cached file
			with open(chapterfile_md, "r") as f:
				chapter_markdown = f.read()
		elif use_cache and os.path.isfile(chapterfile_html):
			# read HTML contents from cache file
			with open(chapterfile_html, "rb") as f:
				html = HTML(html=f.read())
		else:
			# get HTML content from website
			html = session.get(l).html
			
			# store HTML contents within a cache file
			with open(chapterfile_html, "wb") as f:
				f.write(html.raw_html)		

		if chapter_markdown == None:
			# Need to process the HTML contents into markdown
			chapter_markdown = get_chapter_markdown(html)		
			# store generated markdown in a cache file
			with open(chapterfile_md, "w") as f:
				f.write(chapter_markdown)		

		chapter_markdowns.append(chapter_markdown)
	session.close()
	print("  Processed %s chapters, took %s seconds" % (len(chapter_markdowns), round(time.time() - start_time, 3)))
	return chapter_markdowns

def get_chapter_markdown(html_element):
	# title of the html page, used for logging purposes
	html_title = html_element.find("title")[0].text
	# get the title
	try: 
		title = html_element.find("div.section div.section-content div.panel div.caption h4")[0].text
	except:
		title = html_title
		print('\tWARN: title not found for chapter="%s"' % html_title)
	# get all the paragraphs	
	#paragraphs = [p.text.replace("…","...") for p in html_element.find("div.section div.section-content div.p-15 div.fr-view p") if p.text != "" and not p.text.startswith("Previous")]
	paragraphs = [p.raw_html.decode(html_element.encoding).replace("…","...").replace('style=""','') for p in html_element.find("div.section div.section-content div.p-15 div.fr-view p") if p.text != "" and not p.text.startswith("Previous")]
	
	# the first might be similar to the title, therefore it gets excluded
	if "chapter" in paragraphs[0].lower():
		paragraphs = paragraphs[1:]
	if len(paragraphs)<2:
		print('\tWARN: paragraphs not found for chapter="%s"' % html_title)
	# concatenate all the paragraphs
	text = "\n\n".join(paragraphs)
	# generate markdown for this chapter
	chapter_markdown = "# %s\n\n%s\n\n"% (title, text)
	return chapter_markdown

def generate_epub(markdown_file, epub_file, metadata={}):
	start_time = time.time()
	try:
		cmdline = ["pandoc", "--toc", "--to=epub", "--from=markdown", "--output=%s" % epub_file]
		
		if len(metadata) > 0:
			metadata_yaml_file = os.path.join(os.path.dirname(markdown_file), "%s.yml" % os.path.basename(markdown_file))
			with open(metadata_yaml_file, "w") as f:
				f.write("---\n")

				for k,v in metadata.items():
					if isinstance(v, (str, int)):
						f.write('%s: "%s"\n' % (k,v))
				if 'date' not in metadata:
					f.write("date: %s\n" % time.strftime("%Y-%m-%d"))
				f.write("...\n\n")
			
			cmdline.append(metadata_yaml_file)
		
		cmdline.append(markdown_file)
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

def output_chapter_stats(novel, output_file, chapter_markdowns):
	i = 0
	print("Writing chapter length statistics into file %s" % output_file)
	with open(output_file, "w") as f:
		for c in chapter_markdowns:
			i += 1			
			f.write('novel="%s" chapter=%s length=%s\n' % (novel, i, len(c)))

if __name__ == "__main__":
	parser = argparse.ArgumentParser()
	parser.add_argument("novel", help="novel url, as it appears within the browser after 'novel/'")
	parser.add_argument("-n","--nocache", action='store_true', help="If set, avoid using cached content. If not set, the previously downloaded HTML files will be reused.")
	parser.add_argument("-r","--reprocess", action='store_true', help="If set, reprocess the cached HTML content. If not set, the previous processing results will be used")
	parser.add_argument("-s","--split", default=100, type=int, help="Split the novel in multiple ebooks, each <split> chapters long. Set to 0 to generate only one book.")

	args = parser.parse_args()

	novel = args.novel

	overall_start_time = time.time()
	start_time = time.time()

	WUXIA_URL = "https://www.wuxiaworld.com"

	try:
		print('Generating epub for novel "%s"' % novel)

		if args.nocache: print("  NOT using cached HTML files")
		else: print("  Using cached HTML files if present")

		if args.nocache and not args.reprocess:
			print("  Forcing a reprocess, as the cache will not be used")
			args.reprocess = True
		elif args.reprocess: 
			print("  Reprocessing cached HTML files, if present")
		else: 
			print("  Using cached markdown files, if present")

		if args.split > 0: print("  Splitting resulting epub in blocks of %s chapters" % args.split)
		else: print("  Generating only one epub")

		novel_folder = novel 
		novel_data = process_front_matter(novel_url="%s/novel/%s" % (WUXIA_URL, novel), novel=novel, novel_folder=novel_folder)

		#novel_data['chapter_urls'] = novel_data['chapter_urls'][0:102]

		chapter_markdowns = process_chapters(chapter_urls=novel_data['chapter_urls'], novel_folder=novel_folder, use_cache=not args.nocache, reprocess_cached_html=args.reprocess, cache_folder="CACHE")

		# filename of the markdown file generating the epub
		output_md = os.path.join(novel_folder, "%s.md" % novel)
		# filename of the epub. it MUST contain two additional variables for the starting and ending chapter.
		output_epub = os.path.join(novel_folder, "%s_%%s-%%s.epub" % novel)
		
		output_stats = os.path.join(novel_folder, "%s_stats.log" % novel)

		output_chapter_stats(novel=novel, output_file=output_stats, chapter_markdowns=chapter_markdowns)

		if args.split > 0:
			chapter_markdowns = [chapter_markdowns[i:i + args.split] for i in range(0, len(chapter_markdowns), args.split)]
		else:
			chapter_markdowns = [chapter_markdowns]


		print('Generating markdown file')	
		novel_title = novel_data['title']
		count_output_chapters = 0

		for chapter_group in chapter_markdowns:
			start_time = time.time()
			chpt_from = count_output_chapters + 1
			chpt_to = count_output_chapters + len(chapter_group)
				
			with open(output_md, "w") as f:
				f.write("\n\n".join(chapter_group))
			
			print('Markdown generation for chapters %s-%s successful into file="%s", took %s seconds' % (chpt_from, chpt_to, output_md, round(time.time() - start_time,3)))
			#print('Generating epub file')
			novel_data['title'] = "%s - %s-%s" % (novel_title, chpt_from, chpt_to)
			
			generate_epub(markdown_file=output_md, 
				epub_file=output_epub % (chpt_from, chpt_to),
				metadata=novel_data)

			count_output_chapters += len(chapter_group)
				
		print("Done, took %s seconds" % round(time.time() - overall_start_time, 3))
	except KeyboardInterrupt as e:
		print("\nInterrupted: exiting...", file=sys.stderr)
	except ValueError as e:
		#used to communicate that the URL was not found
		print("\nERROR - %s" % e, file=sys.stderr)
	except requests.exceptions.ConnectionError as e:
		print("\nERROR - %s" % e, file=sys.stderr)
	except Exception as e:
		raise(e)
