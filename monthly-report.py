#!/usr/local/bin/python3.7

import yaml
import sys
import traceback
import datetime
import requests
import re
import bs4
import ssl
import smtplib
import json

from email.message import EmailMessage
from email.headerregistry import Address
from email.utils import make_msgid

def main():
	#
	# Load configuration
	with open('config.yaml', 'r') as configFile:
		try:
			config = yaml.safe_load(configFile)
		except:
			traceback.print_exc()
			print("ERROR: could not load config.yaml")
			sys.exit(1)
	#
	# Determine the applicable date range: the previous month
	today = datetime.date.today()
	endDate = today.replace(day=1) - datetime.timedelta(days=1)
	startDate = endDate.replace(day=1)
	monthName = startDate.strftime("%B")
	#
	# Set us up for API requests
	HEADERS = {'Authorization': 'Bearer {}'.format(config['accesstoken'])}
	with requests.Session() as s:
		s.headers.update(HEADERS)
		#
		# Get all the categories
		currencyName = config.get('currency', None)
		url = config['firefly-url'] + '/api/v1/categories'
		categories = s.get(url).json()
		#
		# Get the spent and earned totals for each category
		totals = []
		for category in categories['data']:
			url = config['firefly-url'] + '/api/v1/categories/' + category['id'] + '?start=' + startDate.strftime('%Y-%m-%d') + '&end=' + endDate.strftime('%Y-%m-%d')
			r = s.get(url).json()
			categoryName   = r['data']['attributes']['name']
			# Spent
			categorySpent = 0
			try:
				for c in r['data']['attributes']['spent']:
					if c['currency_code'] == currencyName:
						categorySpent = c['sum']
			except (KeyError, IndexError):
				categorySpent = 0
			# Earned
			categoryEarned = 0
			try:
				for e in r['data']['attributes']['earned']:
					if e['currency_code'] == currencyName:
						categoryEarned = e['sum']
			except (KeyError, IndexError):
				categoryEarned = 0
			categoryTotal  = float(categoryEarned) + float(categorySpent)
			totals.append( {'name': categoryName, 'spent': categorySpent, 'earned': categoryEarned, 'total': categoryTotal} )
		#
		# Get general information
		monthSummary = s.get(config['firefly-url'] + '/api/v1/summary/basic' + '?start=' + startDate.strftime('%Y-%m-%d') + '&end=' + endDate.strftime('%Y-%m-%d')).json()
		yearToDateSummary = s.get(config['firefly-url'] + '/api/v1/summary/basic' + '?start=' + startDate.strftime('%Y') + '-01-01' + '&end=' + endDate.strftime('%Y-%m-%d')).json()

		spentThisMonth     = float(monthSummary['spent-in-'+currencyName]['monetary_value'])
		earnedThisMonth    = float(monthSummary['earned-in-'+currencyName]['monetary_value'])
		netChangeThisMonth = float(monthSummary['balance-in-'+currencyName]['monetary_value'])
		spentThisYear      = float(yearToDateSummary['spent-in-'+currencyName]['monetary_value'])
		earnedThisYear     = float(yearToDateSummary['earned-in-'+currencyName]['monetary_value'])
		netChangeThisYear  = float(yearToDateSummary['balance-in-'+currencyName]['monetary_value'])
		netWorth           = float(yearToDateSummary['net-worth-in-'+currencyName]['monetary_value'])
		#
		# Set up the categories table
		categoriesTableBody = '<table><tr><th>Category</th><th style="text-align: right;">Total</th></tr>'
		#categoriesTableBody = '<table><tr><th>Category</th><th>Spent</th><th>Earned</th><th>Total</th></tr>'
		for category in totals:
			categoriesTableBody += '<tr><td style="padding-right: 1em;">'+category['name']+'</td><td style="text-align: right;">'+str(round(float(category['total']))).replace("-", "−")+'</td></tr>'
			#categoriesTableBody += '<tr><td>'+category['name']+'</td><td>'+str(round(float(category['spent'])))+'</td><td>'+str(round(float(category['earned'])))+'</td><td>'+str(round(float(category['total'])))+'</td></tr>'
		categoriesTableBody += '</table>'
		#
		# Set up the general information table
		generalTableBody = '<table>'
		generalTableBody += '<tr><td>Spent this month:</td><td style="text-align: right;">' + str(round(spentThisMonth)).replace("-", "−") + '</td></tr>'
		generalTableBody += '<tr><td>Earned this month:</td><td style="text-align: right;">' + str(round(earnedThisMonth)).replace("-", "−") + '</td></tr>'
		generalTableBody += '<tr style="border-bottom: 1px solid black"><td>Net change this month:</td><td style="text-align: right;">' + str(round(netChangeThisMonth)).replace("-", "−") + '</td></tr>'
		generalTableBody += '<tr><td>Spent so far this year:</td><td style="text-align: right;">' + str(round(spentThisYear)).replace("-", "−") + '</td></tr>'
		generalTableBody += '<tr><td>Earned so far this year:</td><td style="text-align: right;">' + str(round(earnedThisYear)).replace("-", "−") + '</td></tr>'
		generalTableBody += '<tr style="border-bottom: 1px solid black"><td style="padding-right: 1em;">Net change so far this year:</td><td style="text-align: right;">' + str(round(netChangeThisYear)).replace("-", "−") + '</td></tr>'
		generalTableBody += '<tr><td>Current net worth:</td><td style="text-align: right;">' + str(round(netWorth)).replace("-", "−") + '</td></tr>'
		generalTableBody +='</table>'
		#
		# Assemble the email
		msg = EmailMessage()
		msg['Subject'] = f"Firefly III: Monthly report in {currencyName}"
		msg['From'] = "monthly-report <" + config['email']['from'] + ">"
		msg['To'] = ( tuple(config['email']['to']) )
		htmlBody = """
		<html>
			<head>
				<style>table{{border-collapse: collapse; border-top: 1px solid black; border-bottom: 1px solid black;}} th {{border-bottom: 1px solid black; padding: 0.33em 1em 0.33em 1em;}} td{{padding: .1em;}} tr:nth-child(even) {{background: #EEE}} tr:nth-child(odd) {{background: #FFF}}</style>
			</head>
			<body>
				<p>Monthly report for {monthName} {year} in {currency}:</p>
				{categoriesTableBody}
				<p>General information:</p>
				{generalTableBody}
			</body>
		</html>
		""".format( monthName=monthName, year=startDate.strftime("%Y"), currency=currencyName, categoriesTableBody=categoriesTableBody, generalTableBody=generalTableBody )
		msg.set_content(bs4.BeautifulSoup(htmlBody, "html.parser").get_text()) # just html to text
		msg.add_alternative(htmlBody, subtype='html')
		#
		# Set up the SSL context for SMTP if necessary
		context = ssl.create_default_context()
		#
		# Send off the message
		if config['smtp']['starttls']:
			with smtplib.SMTP_SSL(config['smtp']['server'], config['smtp']['port'], context=context) as s:
				sendMessage(s, config, msg)
		else:
			with smtplib.SMTP(config['smtp']['server'], config['smtp']['port']) as s:
				sendMessage(s, config, msg)

def sendMessage(s, config, msg):
	if config['smtp']['authentication']:
		try:
			s.login(user=config['smtp']['user'], password=config['smtp']['password'])
		except:
			traceback.print_exc()
			print("ERROR: could not authenticate with SMTP server.")
			sys.exit(3)
	s.send_message(msg)

if __name__ == "__main__":
	main()
