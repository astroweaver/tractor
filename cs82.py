import os
import time
import logging
import matplotlib
matplotlib.use('Agg')
import numpy as np
import pylab as plt
from glob import glob
from astrometry.util.pyfits_utils import *
from astrometry.util.sdss_radec_to_rcf import *
from astrometry.util.multiproc import *
from astrometry.util.file import *
from astrometry.util.util import *
from astrometry.sdss import *
from tractor import *
from tractor import cfht as cf
from tractor import sdss as st
from tractor.sdss_galaxy import *
from tractor.emfit import em_fit_2d
from tractor.fitpsf import em_init_params
import emcee

def getdata():
	fn = 'cs82data/W4p1m1_i.V2.7A.swarp.cut.vig15_deV_ord2_size25.fits'
	T = fits_table(fn, hdunum=2)
	print 'Read', len(T), 'rows from', fn
	#T.about()

	r0,r1,d0,d1 = T.alpha_sky.min(), T.alpha_sky.max(), T.delta_sky.min(), T.delta_sky.max()
	print 'Range', r0,r1,d0,d1
	plt.clf()
	plt.plot(T.alpha_sky, T.delta_sky, 'r.')
	plt.xlabel('alpha_sky')
	plt.ylabel('delta_sky')

	rcf = radec_to_sdss_rcf((r0+r1)/2., (d0+d1)/2., radius=60., tablefn='s82fields.fits')
	print 'SDSS fields nearby:', len(rcf)

	rr = [ra  for r,c,f,ra,dec in rcf]
	dd = [dec for r,c,f,ra,dec in rcf]
	plt.plot(rr, dd, 'k.')
	plt.savefig('rd.png')

	RA,DEC = 334.4, 0.3

	rcf = radec_to_sdss_rcf(RA,DEC, radius=10., tablefn='s82fields.fits',
							 contains=True)
	print 'SDSS fields nearby:', len(rcf)
	rcf = [(r,c,f,ra,dec) for r,c,f,ra,dec in rcf if r != 206]
	print 'Filtering out run 206:', len(rcf)

	sdss = DR7()
	sdss.setBasedir('cs82data')
	for r,c,f,ra,dec in rcf:
		for band in 'ugriz':
			print 'Retrieving', r,c,f,band
			st.get_tractor_image(r, c, f, band, psf='dg', useMags=True, sdssobj=sdss)

	plt.clf()
	plt.plot(T.alpha_sky, T.delta_sky, 'r.')
	plt.xlabel('alpha_sky')
	plt.ylabel('delta_sky')
	rr = [ra  for r,c,f,ra,dec in rcf]
	dd = [dec for r,c,f,ra,dec in rcf]
	plt.plot(rr, dd, 'k.')
	#RR,DD = [],[]
	keepWCS = []
	for j,fn in enumerate(glob('cs82data/86*p.fits')):
	# for j,fn in enumerate(glob('cs82data/86*p-21.fits')):
		for i in range(36):
		# for i in [-1]:
			wcs = anwcs(fn, i+1)
			#WCS.append(wcs)
			#print 'image size', wcs.imagew, wcs.imageh
			rr,dd = [],[]
			W,H = wcs.imagew, wcs.imageh
			for x,y in [(1,1),(W,1),(W,H),(1,H),(1,1)]:
				r,d = wcs.pixelxy2radec(x,y)
				rr.append(r)
				dd.append(d)
			rc,dc = wcs.pixelxy2radec(W/2,H/2)
			tc = '%i:%i' % (j,i)
			if wcs.is_inside(RA,DEC):
				keepWCS.append(wcs)
				print 'Keeping', tc
			#RR.append(rr)
			#DD.append(dd)
			plt.plot(rr,dd, 'b-')
			plt.text(rc,dc,tc, color='b')
	#plt.plot(np.array(RR).T, np.array(DD).T, 'b-')
	plt.savefig('rd2.png')


def get_cfht_image(fn, psffn, pixscale, RA, DEC, sz, bandname=None,
				   filtermap=None):
	if filtermap is None:
		filtermap = {'i.MP9701': 'i'}
	wcs = Tan(fn, 0)
	x,y = wcs.radec2pixelxy(RA,DEC)
	print 'x,y', x,y
	S = int(sz / pixscale) / 2
	print '(half) S', S
	cfx,cfy = int(x),int(y)
	cfroi = [cfx-S, cfx+S, cfy-S, cfy+S]
	#cfroi = [cfx-S*2, cfx+S*2, cfy-S, cfy+S]
	x0,x1,y0,y1 = cfroi

	#wcs = FitsWcs(wcs)
	#wcs = RotatedFitsWcs(wcs)
	#wcs.setX0Y0(x0+1., y0+1.)

	P = pyfits.open(fn)
	I = P[1].data
	print 'Img data', I.shape
	roislice = (slice(y0,y1), slice(x0,x1))
	image = I[roislice]
	sky = np.median(image)
	print 'Sky', sky
	# save for later...
	cfsky = sky
	skyobj = ConstantSky(sky)
	# Third plane in image: variance map.
	I = P[3].data
	var = I[roislice]
	cfstd = np.sqrt(np.median(var))

	# Add source noise...
	phdr = P[0].header
	# e/ADU
	gain = phdr.get('GAIN')
	# Poisson statistics are on electrons; var = mean
	el = np.maximum(0, (image - sky) * gain)
	# var in ADU...
	srcvar = el / gain**2
	invvar = 1./(var + srcvar)

	# Apply mask
	# MP_BAD  =                    0
	# MP_SAT  =                    1
	# MP_INTRP=                    2
	# MP_CR   =                    3
	# MP_EDGE =                    4
	# HIERARCH MP_DETECTED =       5
	# HIERARCH MP_DETECTED_NEGATIVE = 6
	I = P[2].data.astype(np.uint16)
	#print 'I:', I
	#print I.dtype
	mask = I[roislice]
	#print 'Mask:', mask
	hdr = P[2].header
	badbits = [hdr.get('MP_%s' % nm) for nm in ['BAD', 'SAT', 'INTRP', 'CR']]
	print 'Bad bits:', badbits
	badmask = sum([1 << bit for bit in badbits])
	#print 'Bad mask:', badmask
	#print 'Mask dtype', mask.dtype
	invvar[(mask & int(badmask)) > 0] = 0.
	del I
	del var

	psfimg = pyfits.open(psffn)[0].data
	print 'PSF image shape', psfimg.shape
	# number of Gaussian components
	PS = psfimg.shape[0]
	K = 3
	w,mu,sig = em_init_params(K, None, None, None)
	II = psfimg.copy()
	II /= II.sum()
	# HACK
	II = np.maximum(II, 0)
	print 'Multi-Gaussian PSF fit...'
	xm,ym = -(PS/2), -(PS/2)
	em_fit_2d(II, xm, ym, w, mu, sig)
	print 'w,mu,sig', w,mu,sig
	psf = GaussianMixturePSF(w, mu, sig)

	if bandname is None:
		# try looking up in filtermap.
		filt = phdr['FILTER']
		if filt in filtermap:
			print 'Mapping filter', filt, 'to', filtermap[filt]
			bandname = filtermap[filt]
		else:
			print 'No mapping found for filter', filt
			bandname = flit

	photocal = cf.CfhtPhotoCal(hdr=phdr, bandname=bandname)

	filename = phdr['FILENAME'].strip()

	(H,W) = image.shape
	print 'Image shape', W, H
	print 'x0,y0', x0,y0
	print 'Original WCS:', wcs
	rdcorners = [wcs.pixelxy2radec(x+x0,y+y0) for x,y in [(1,1),(W,1),(W,H),(1,H)]]
	print 'Original RA,Dec corners:', rdcorners
	wcs = crop_wcs(wcs, x0, y0, W, H)
	print 'Cropped WCS:', wcs
	rdcorners = [wcs.pixelxy2radec(x,y) for x,y in [(1,1),(W,1),(W,H),(1,H)]]
	print 'cropped RA,Dec corners:', rdcorners
	wcs = rot90_wcs(wcs, W, H)
	print 'Rotated WCS:', wcs
	rdcorners = [wcs.pixelxy2radec(x,y) for x,y in [(1,1),(H,1),(H,W),(1,W)]]
	print 'rotated RA,Dec corners:', rdcorners

	wcs = FitsWcs(wcs)
	wcs.setX0Y0(1., 1.)

	image = np.rot90(image, k=1)
	invvar = np.rot90(invvar, k=1)
							   
	cftimg = Image(data=image, invvar=invvar, psf=psf, wcs=wcs,
				   sky=skyobj, photocal=photocal, name='CFHT %s' % filename)
	return cftimg, cfsky, cfstd

def crop_wcs(wcs, x0, y0, W, H):
	out = Tan()
	out.set_crval(wcs.crval[0], wcs.crval[1])
	out.set_crpix(wcs.crpix[0] - x0, wcs.crpix[1] - y0)
	cd = wcs.get_cd()
	out.set_cd(*cd)
	out.imagew = W
	out.imageh = H
	return out

def rot90_wcs(wcs, W, H):
	out = Tan()
	out.set_crval(wcs.crval[0], wcs.crval[1])
	out.set_crpix(wcs.crpix[1], W+1 - wcs.crpix[0])
	cd = wcs.get_cd()
	out.set_cd(cd[1], -cd[0], cd[3], -cd[2])
	out.imagew = wcs.imageh
	out.imageh = wcs.imagew
	# opposite direction:
	#out.set_crpix(H+1 - wcs.crpix[1], wcs.crpix[0])
	#out.set_cd(-cd[1], cd[0], -cd[3], cd[2])
	return out


def get_tractor(RA, DEC, sz, cffns, filtermap=None, sdssbands=None):
	if sdssbands is None:
		sdssbands = ['u','g','r','i','z']
	tractor = Tractor()

	skies = []
	pixscale = 0.187
	print 'CFHT images:', cffns
	for fn in cffns:
		psffn = fn.replace('-cr', '-psf')
		cfimg,cfsky,cfstd = get_cfht_image(fn, psffn, pixscale, RA, DEC, sz,
										   filtermap=filtermap)
		tractor.addImage(cfimg)
		skies.append((cfsky, cfstd))

	pixscale = 0.396
	S = int(sz / pixscale)
	print 'SDSS size:', S
	rcf = radec_to_sdss_rcf(RA,DEC, radius=10., tablefn='s82fields.fits', contains=True)
	print 'SDSS fields nearby:', len(rcf)
	rcf = [(r,c,f,ra,dec) for r,c,f,ra,dec in rcf if r != 206]
	print 'Filtering out run 206:', len(rcf)

	# rcf = rcf[:16]
	# rcf = rcf[:4]
	# rcf = rcf[:1]
	sdss = DR7()
	sdss.setBasedir('cs82data')
	i = 0
	for r,c,f,ra,dec in rcf:
		for band in sdssbands:
			print 'Retrieving', r,c,f,band
			fn = 'sdss-psf-%03i.png' % i
			i += 1
			print fn
			im,info = st.get_tractor_image(r, c, f, band, psf='kl-gm', useMags=True,
										   sdssobj=sdss, roiradecsize=(RA,DEC,S/2),
										   savepsfimg=fn)
			print 'Image size', im.getWidth(), im.getHeight()
			if im.getWidth() == 0 or im.getHeight() == 0:
				continue
			tractor.addImage(im)
			skies.append((info['sky'], info['skysig']))

	return tractor,skies

def mysavefig(fn):
	plt.savefig(fn)
	print 'Wrote', fn


def read_cf_catalogs(RA, DEC, sz):
	fn = 'cs82data/W4p1m1_i.V2.7A.swarp.cut.vig15_deV_ord2_size25.fits'
	T = fits_table(fn, hdunum=2)
	print 'Read', len(T), 'rows from', fn
	T.ra  = T.alpha_sky
	T.dec = T.delta_sky

	fn = 'cs82data/W4p1m1_i.V2.7A.swarp.cut.vig15_exp_ord2_size25.fit'
	T2 = fits_table(fn, hdunum=2)
	print 'Read', len(T2), 'rows from', fn
	T2.ra  = T2.alpha_sky
	T2.dec = T2.delta_sky

	# approx...
	S = sz / 3600.
	ra0 ,ra1  = RA-S/2.,  RA+S/2.
	dec0,dec1 = DEC-S/2., DEC+S/2.

	if False:
		T = T[np.logical_or(T.mag_model < 50, T.mag_psf < 50)]
		Tstar = T[np.logical_and(T.chi2_psf < T.chi2_model, T.mag_psf < 50)]
		Tgal = T[np.logical_and(T.chi2_model < T.chi2_psf, T.mag_model < 50)]
		# 'mag_psf', 'chi2_psf',
		for i,c in enumerate(['mag_model', 'chi2_model', 
							  'spheroid_reff_world', 'spheroid_aspect_world',
							  'spheroid_theta_world']):
			plt.clf()
			plt.hist(Tgal.get(c), 100)
			plt.xlabel(c)
			mysavefig('hist%i.png' % i)
		sys.exit(0)

		plt.clf()
		plt.semilogx(T.chi2_psf, T.chi2_psf - T.chi2_model, 'r.')
		plt.ylim(-100, 100)
		plt.xlabel('chi2_psf')
		plt.ylabel('chi2_psf - chi2_model')
		mysavefig('chi.png')

	for c in ['disk_scale_world', 'disk_aspect_world', 'disk_theta_world']:
		T.set(c, T2.get(c))
	T.ra_disk  = T2.alphamodel_sky
	T.dec_disk = T2.deltamodel_sky
	T.mag_disk = T2.mag_model
	T.chi2_disk = T2.chi2_model
	T.ra_sph  = T2.alphamodel_sky
	T.dec_sph = T2.deltamodel_sky
	T.mag_sph = T.mag_model
	T.chi2_sph = T.chi2_model

	T = T[(T.ra > ra0) * (T.ra < ra1) * (T.dec > dec0) * (T.dec < dec1)]
	print 'Cut to', len(T), 'objects nearby.'

	T.chi2_gal = np.minimum(T.chi2_disk, T.chi2_sph)
	T.mag_gal = np.where(T.chi2_disk < T.chi2_sph, T.mag_disk, T.mag_sph)

	Tstar = T[np.logical_and(T.chi2_psf < T.chi2_gal, T.mag_psf < 50)]
	Tgal = T[np.logical_and(T.chi2_gal < T.chi2_psf, T.mag_gal < 50)]
	print len(Tstar), 'stars'
	print len(Tgal), 'galaxies'
	Tdisk = Tgal[Tgal.chi2_disk < Tgal.chi2_sph]
	Tsph  = Tgal[Tgal.chi2_sph  <= Tgal.chi2_disk]
	print len(Tdisk), 'disk'
	print len(Tsph), 'spheroid'

	return Tstar, Tdisk, Tsph

def get_cf_sources(Tstar, Tdisk, Tsph, magcut=100, mags=['u','g','r','i','z']):
	srcs = []
	for t in Tdisk:
		# xmodel_world == alphamodel_sky
		if t.mag_disk > magcut:
			#print 'Skipping source with mag=', t.mag_disk
			continue
		#origwcs = Tan(cffns[0],0)
		#x,y = origwcs.radec2pixelxy(t.alphamodel_sky, t.deltamodel_sky)
		#print 'WCS x,y', x,y
		#print '    x,y', t.xmodel_image, t.ymodel_image
		#print '    del', t.xmodel_image - x, t.ymodel_image - y
		#print '    x,y', t.x_image, t.y_image
		m = Mags(order=mags, **dict([(k, t.mag_disk) for k in mags]))
		src = DevGalaxy(RaDecPos(t.ra_disk, t.dec_disk), m,
						GalaxyShape(t.disk_scale_world * 3600., t.disk_aspect_world,
									t.disk_theta_world + 90.))
		#print 'Adding source', src
		srcs.append(src)
	for t in Tsph:
		if t.mag_sph > magcut:
			#print 'Skipping source with mag=', t.mag_sph
			continue
		m = Mags(order=mags, **dict([(k, t.mag_sph) for k in mags]))
		src = ExpGalaxy(RaDecPos(t.ra_sph, t.dec_sph), m,
						GalaxyShape(t.spheroid_reff_world * 3600., t.spheroid_aspect_world,
									t.spheroid_theta_world + 90.))
		#print 'Adding source', src
		srcs.append(src)
	assert(len(Tstar) == 0)
	return srcs

def tweak_wcs((tractor, im)):
	#print 'Tractor', tractor
	#print 'Image', im
	tractor.images = Images(im)
	print 'tweak_wcs: fitting params:', tractor.getParamNames()
	for step in range(10):
		print 'Run optimization step', step
		t0 = Time()
		dlnp,X,alpha = tractor.opt2(alphas=[0.5, 1., 2., 4.])
		t_opt = (Time() - t0)
		print 'alpha', alpha
		print 'Optimization took', t_opt, 'sec'
		lnp0 = tractor.getLogProb()
		print 'Lnprob', lnp0
		if dlnp == 0:
			break
	return im.getParams()

def plot1((tractor, i, zr, plotnames, step, pp, ibest)):
	plt.figure(figsize=(6,6))
	plt.clf()
	plotpos0 = [0.01, 0.01, 0.98, 0.94]
	ima = dict(interpolation='nearest', origin='lower',
			   vmin=zr[0], vmax=zr[1], cmap='gray')
	imchi = dict(interpolation='nearest', origin='lower',
				 vmin=-5., vmax=+5., cmap='gray')
	imchi2 = dict(interpolation='nearest', origin='lower',
				  vmin=-50., vmax=+50., cmap='gray')
	tim = tractor.getImage(i)
	if 'data' in plotnames:
		data = tim.getImage()
		plt.clf()
		plt.gca().set_position(plotpos0)
		myimshow(data, **ima)
		plt.title('Data %s' % tim.name)
		plt.xticks([],[])
		plt.yticks([],[])
		mysavefig('data-%02i.png' % i)

	if 'dataann' in plotnames and i == 0:
		ax = plt.axis()
		xy = np.array([tim.getWcs().positionToPixel(s.getPosition())
					   for s in tractor.catalog])
		plt.plot(xy[:,0], xy[:,1], 'r+')
		plt.axis(ax)
		mysavefig('data-%02i-ann.png' % i)

	if 'modbest' in plotnames or 'chibest' in plotnames:
		pbest = pp[ibest,:]
		tractor.setParams(pp[ibest,:])
		if 'modbest' in plotnames:
			mod = tractor.getModelImage(i)
			plt.clf()
			plt.gca().set_position(plotpos0)
			myimshow(mod, **ima)
			plt.title('Model (best)')
			plt.xticks([],[])
			plt.yticks([],[])
			mysavefig('modbest-%02i-%02i.png' % (i,step))
		if 'chibest' in plotnames:
			chi = tractor.getChiImage(i)
			plt.imshow(chi, **imchi)
			plt.title('Chi (best)')
			plt.xticks([],[])
			plt.yticks([],[])
			mysavefig('chibest-%02i-%02i.png' % (i,step))

			plt.imshow(chi, **imchi2)
			plt.title('Chi (best)')
			plt.xticks([],[])
			plt.yticks([],[])
			mysavefig('chibest2-%02i-%02i.png' % (i,step))

	if 'modsum' in plotnames or 'chisum' in plotnames:
		modsum = None
		chisum = None
		if pp is None:
			pp = np.array([tractor.getParams()])
		nw = len(pp)
		print 'modsum/chisum plots for', nw, 'walkers'
		for k in xrange(nw):
			tractor.setParams(pp[k,:])
			mod = tractor.getModelImage(i)
			chi = tractor.getChiImage(i)
			if k == 0:
				modsum = mod
				chisum = chi
			else:
				modsum += mod
				chisum += chi

		if 'modsum' in plotnames:
			plt.clf()
			plt.gca().set_position(plotpos0)
			myimshow(modsum/float(nw), **ima)
			plt.title('Model (sum)')
			plt.xticks([],[])
			plt.yticks([],[])
			mysavefig('modsum-%02i-%02i.png' % (i,step))
		if 'chisum' in plotnames:
			plt.clf()
			plt.gca().set_position(plotpos0)
			plt.imshow(chisum/float(nw), **imchi)
			plt.title('Chi (sum)')
			plt.xticks([],[])
			plt.yticks([],[])
			mysavefig('chisum-%02i-%02i.png' % (i,step))
			plt.imshow(chisum/float(nw), **imchi2)
			plt.title('Chi (sum)')
			plt.xticks([],[])
			plt.yticks([],[])
			mysavefig('chisum2-%02i-%02i.png' % (i,step))

def plots(tractor, plotnames, step, pp=None, mp=None, ibest=None, imis=None, alllnp=None):
	if 'lnps' in plotnames:
		plotnames.remove('lnps')
		plt.figure(figsize=(6,6))
		plt.clf()
		plotpos0 = [0.15, 0.15, 0.84, 0.80]
		plt.gca().set_position(plotpos0)
		for s,lnps in enumerate(alllnp):
			plt.plot(np.zeros_like(lnps)+s, lnps, 'r.')
		plt.savefig('lnps-%02i.png' % step)

	args = []
	if imis is None:
		imis = range(len(tractor.getImages()))
	NI = len(tractor.getImages())
	for i in imis:
		if i >= NI:
			print 'Skipping plot of image', i, 'with N images', NI
			continue
		zr = tractor.getImage(i).zr
		args.append((tractor, i, zr, plotnames, step, pp, ibest))
	if mp is None:
		map(plot1, args)
	else:
		mp.map(plot1, args)


def nlmap(X):
	S = 0.01
	return np.arcsinh(X * S)/S
def myimshow(x, *args, **kwargs):
	mykwargs = kwargs.copy()
	if 'vmin' in kwargs:
		mykwargs['vmin'] = nlmap(kwargs['vmin'])
	if 'vmax' in kwargs:
		mykwargs['vmax'] = nlmap(kwargs['vmax'])
	return plt.imshow(nlmap(x), *args, **mykwargs)

def getlnp((tractor, i, par0, step)):
	tractor.setParam(i, par0+step)
	lnp = tractor.getLogProb()
	tractor.setParam(i, par0)
	return lnp


dpool = None
def pool_stats():
	if dpool is None:
		return
	print 'Total pool CPU time:', dpool.get_worker_cpu()
	
def main():
	#getdata()

	import optparse
	parser = optparse.OptionParser()
	parser.add_option('--threads', dest='threads', default=16, type=int, help='Use this many concurrent processors')
	parser.add_option('-v', '--verbose', dest='verbose', action='count', default=0,
					  help='Make more verbose')
	parser.add_option('-f', '--force-stage', dest='force', action='append', default=[], type=int,
					  help="Force re-running the given stage(s) -- don't read from pickle.")
	parser.add_option('-s', '--stage', dest='stage', default=4, type=int,
					  help="Run up to the given stage")
	opt,args = parser.parse_args()

	if opt.verbose == 0:
		lvl = logging.INFO
	else:
		lvl = logging.DEBUG
	logging.basicConfig(level=lvl, format='%(message)s', stream=sys.stdout)

	import debugpool
	global dpool
	dpool = debugpool.DebugPool(opt.threads)
	Time.add_measurement(DebugPoolMeas(dpool))
	mp = multiproc(pool=dpool)
	#mp = multiproc(opt.threads)

	RA,DEC = 334.4, 0.3
	sz = 2.*60. # arcsec

	plotims = [0,1,2,3, 7,8,9]
	plotsa = dict(imis=plotims, mp=mp)

	def cut_bright(cat, magcut=24):
		brightcat = Catalog()
		I = []
		mags = []
		for i,src in enumerate(cat):
			mag = src.getBrightness().i
			if mag < magcut:
				#brightcat.append(src)
				I.append(i)
				mags.append(mag)
		J = np.argsort(mags)
		I = np.array(I)
		I = I[J]
		for i in I:
			brightcat.append(cat[i])
		return brightcat, I

	# Read image files and catalogs, make Tractor object.
	def stage00(mp=None):
		cffns = glob('cs82data/86*p-21-cr.fits')
		# Don't map them to the same mag as SDSS i-band
		filtermap = {'i.MP9701': 'i2'}
		#sdssbands = ['u','g','r','i','z']
		sdssbands = ['g','r','i']
		tractor,skies = get_tractor(RA,DEC,sz, cffns, filtermap=filtermap, sdssbands=sdssbands)
		Tstar,Tdisk,Tsph = read_cf_catalogs(RA, DEC, sz)
		srcs = get_cf_sources(Tstar, Tdisk, Tsph, mags=sdssbands + ['i2'])
		tractor.addSources(srcs)
		for im,(sky,skystd) in zip(tractor.getImages(), skies):
			# for display purposes...
			im.skylevel = sky
			im.skystd = skystd
			im.zr = np.array([-1.,+20.]) * skystd + sky
			#im.zrs = [np.array([-1.,+20.]) * std + sky for sky,std in skies]
		plots(tractor, ['data'], 0, **plotsa)
		return dict(tractor=tractor, skies=skies)

	def stage01(tractor=None, mp=None, step0=0, thaw_wcs=['crval1','crval2'],
				#thaw_sdss=['a','d'],
				thaw_sdss=[],
				**kwargs):
		print 'tractor', tractor
		tractor.mp = mp
		# For the initial WCS alignment, cut to brightish sources...
		allsources = tractor.getCatalog()
		brightcat,nil = cut_bright(allsources)
		tractor.setCatalog(brightcat)
		print 'Cut to', len(brightcat), 'bright sources', brightcat.numberOfParams(), 'params'
		allims = tractor.getImages()
		fitims = []
		for im in allims:
			im.freezeParams('photocal', 'psf', 'sky')
			if hasattr(im.wcs, 'crval1'):
				# FitsWcs:
				im.wcs.freezeAllBut(*thaw_wcs)
			elif len(thaw_sdss):
				# SdssWcs: equivalent is 'a','d'
				im.wcs.freezeAllBut(*thaw_sdss)
			else:
				continue
			fitims.append(im)
		print len(tractor.getImages()), 'images', tractor.images.numberOfParams(), 'image params'
		tractor.freezeParam('catalog')

		lnp0 = tractor.getLogProb()
		print 'Lnprob', lnp0
		plots(tractor, ['modsum', 'chisum'], step0 + 0, **plotsa)

		#wcs0 = tractor.getParams()
		wcs0 = np.hstack([im.getParams() for im in fitims])
		print 'Orig WCS:', wcs0
		# We will tweak the WCS parameters one image at a time...
		tractor.images = Images()
		# Do the work:
		wcs1 = mp.map(tweak_wcs, [(tractor,im) for im in fitims], wrap=True)
		# Reset the images
		tractor.setImages(allims)
		# Save the new WCS params!
		for im,p in zip(fitims,wcs1):
			im.setParams(p)
		lnp1 = tractor.getLogProb()
		print 'Before lnprob', lnp0
		print 'After  lnprob', lnp1
		wcs1 = np.hstack(wcs1)
		print 'Orig WCS:', wcs0
		print 'Opt  WCS:', wcs1
		print 'dWCS (arcsec):', (wcs1 - wcs0) * 3600.
		plots(tractor, ['modsum', 'chisum'], step0 + 1, None, **plotsa)

		# Re-freeze WCS
		for im in tractor.getImages():
			im.wcs.thawAllParams()
			im.freezeParam('wcs')
		tractor.unfreezeParam('catalog')

		tractor.setCatalog(allsources)
		return dict(tractor=tractor)

	# Also fit the WCS rotation matrix (CD) terms.
	def stage02(tractor=None, mp=None, **kwargs):
		for i,im in enumerate(tractor.getImages()):
			#print 'Tractor image i:', im.name
			#print 'Params:', im.getParamNames()
			im.unfreezeAllParams()
			#print 'Params:', im.getParamNames()
		stage01(tractor=tractor, mp=mp, step0=2,
				thaw_wcs=['crval1', 'crval2', 'cd1_1', 'cd1_2', 'cd2_1', 'cd2_2'],
				#thaw_sdss=['a','d','b','c','e','f'],
				**kwargs)
		return dict(tractor=tractor)

	def stage03old(tractor=None, mp=None, **kwargs):
		print 'Tractor:', tractor
		#print ' catalog:', len(tractor.getCatalog()), 'sources',
		#print tractor.getCatalog().numberOfParams(), 'params'
		print ' catalog:', tractor.getCatalog()

		# allsources = tractor.getCatalog()
		# brightcat = cut_bright(allsources, magcut=22)
		# tractor.setCatalog(brightcat)
		# print ' Cut to:', tractor.getCatalog()

		tractor.freezeParam('images')
		tractor.catalog.thawParamsRecursive('*')
		print ' Catalog:', tractor.getCatalog()
		print 'Tractor params:', tractor.numberOfParams()
		
		p0 = np.array(tractor.getParams())
		steps = np.array(tractor.getStepSizes())
		pnames = np.array(tractor.getParamNames())

		# Calibrate the step sizes...
		print 'Checking step sizes...'
		lnp0 = tractor.getLogProb()
		lnps = mp.map(getlnp, [(tractor, i, par0, step) for i,(par0,step)
							   in enumerate(zip(p0, steps))])
		lnps = np.array(lnps)
		dlnps = np.abs(lnps - lnp0)

		for cc in range(5):
			I = np.flatnonzero((dlnps != 0) * np.logical_or(dlnps < 0.5, dlnps > 2.))
			print 'Trying', len(I), 'different step sizes'
			scale = np.sqrt(dlnps[I])
			scale = np.clip(scale, 1e-2, 1e2)
			s2 = steps[I] / scale
			lnps2 = mp.map(getlnp, [(tractor, i, par0, step) for (i,par0,step)
									in zip(I, p0[I], s2)])
			lnps2 = np.array(lnps2)
			dlnps2 = np.abs(lnps2 - lnp0)
			f1 = np.maximum(dlnps[I], 1./dlnps[I])
			f2 = np.maximum(dlnps2, 1./dlnps2)
			keep = (f2 < f1)
			print 'Keeping', sum(keep), 'changes of step size'
			dlnps2 = dlnps2[keep]
			s2 = s2[keep]
			I = I[keep]
			for i,d,s in zip(I,dlnps2,s2):
				print '  ', pnames[i], 'step', steps[i], 'dlnp', dlnps[i],
				print '-> step', s, 'dlnp', d
			steps[I] = s2
			dlnps = dlnps2
		return dict(tractor=tractor, steps=steps)

	def stage03old2(tractor=None, mp=None, steps=None, **kwargs):
		print 'Tractor:', tractor
		tractor.mp = mp
		tractor.freezeParam('images')
		tractor.catalog.thawParamsRecursive('*')
		# Am I going to be better to literally cut the catalog, or freeze faint sources?
		allsources = tractor.getCatalog()
		brightcat,Ibright = cut_bright(allsources, magcut=23)
		tractor.setCatalog(brightcat)
		print ' Cut to:', tractor.getCatalog()

		# # Find indices of the params of bright sources.
		# bparams = []
		# keep = np.zeros(len(allsources), bool)
		# keep[Ibright] = True
		# ii = 0
		# for i,src in enumerate(allsources):
		# 	N = src.numberOfParams()
		# 	if keep[i]:
		# 		bparams.append(steps[ii:ii+N])
		# 	ii += N
		# assert(ii == allsources.numberOfParams())
		# bparams = np.hstack(bparams)
		# assert(len(bparams) == tractor.catalog.numberOfParams())
		# steps = steps[bparams]
		# assert(len(steps) == tractor.catalog.numberOfParams())

		p0 = np.array(tractor.getParams())
		pnames = np.array(tractor.getParamNames())

		ndim = len(p0)
		nw = 32

		sampler = emcee.EnsembleSampler(nw, ndim, tractor, pool = mp.pool,
										live_dangerously=True)
		mhsampler = emcee.EnsembleSampler(nw, ndim, tractor, pool = mp.pool,
										  live_dangerously=True)

		# Scale step sizes until we get small lnp changes
		psteps = 1e-7 * np.array(tractor.getStepSizes())
		while True:
			pp = emcee.EnsembleSampler.sampleBall(p0, psteps, nw)
			# Put one walker at the nominal position.
			pp[0,:] = p0
			lnp = np.array(mp.map(tractor, pp))
			dlnp = lnp - np.max(lnp)
			print 'dlnp min', np.min(dlnp), 'median', np.median(dlnp)
			if np.median(dlnp) > -10:
				break
			psteps *= 0.1

		rstate = None
		alllnp = []
		allp = []

		for step in range(1, 101):
			allp.append(pp)

			if step % 10 == 0:
				ibest = np.argmax(lnp)
				plots(tractor, ['modsum', 'chisum', 'modbest', 'chibest'],
					  step, pp=pp, ibest=ibest, **plotsa)

			print 'Run MCMC step', step
			kwargs = dict(storechain=False)
			# Alternate 5 steps of stretch move, 5 steps of MH.
			t0 = Time()
			if step % 10 >= 5:
				print 'Using MH proposal'
				kwargs['mh_proposal'] = emcee.MH_proposal_axisaligned(psteps)
				pp,lnp,rstate = mhsampler.run_mcmc(pp, 1, lnprob0=lnp, rstate0=rstate, **kwargs)
			else:
				pp,lnp,rstate = sampler.run_mcmc(pp, 1, lnprob0=lnp, rstate0=rstate, **kwargs)
			t_mcmc = (Time() - t0)
			#print 'lnprobs:', lnp
			print 'Best lnprob:', np.max(lnp)
			print 'dlnprobs:', ', '.join(['%.1f' % d for d in lnp - np.max(lnp)])
			print 'MCMC took', t_mcmc, 'sec'

			if sampler.iterations:
				print 'Running acceptance fraction: emcee', sampler.acceptance_fraction
				print 'mean', np.mean(sampler.acceptance_fraction)
			if mhsampler.iterations:
				print 'Running acceptance fraction: MH', mhsampler.acceptance_fraction
				print 'mean', np.mean(mhsampler.acceptance_fraction)

			# Tweak step sizes...
			print 'Walker stdevs / psteps:'
			st = np.std(pp, axis=0)
			f = st / np.abs(psteps)
			print '  median', np.median(f)
			print '  range', np.min(f), np.max(f)
			# Adjust the "psteps" toward the stdev by small factors.
			# Note that this is per-parameter.
			mx = 1.2
			tweak = np.clip(f, 1./mx, mx)
			psteps *= tweak
			print 'After tweaking:'
			f = st / np.abs(psteps)
			print '  median', np.median(f)
			print '  range', np.min(f), np.max(f)

			if step % 2 == 0:
				# Resample walkers that are doing badly
				bestlnp = np.max(lnp)
				dlnp = lnp - bestlnp
				cut = -20
				I = np.flatnonzero(dlnp < cut)
				print len(I), 'walkers have lnprob more than', -cut, 'worse than the best'
				if len(I):
					ok = np.flatnonzero(dlnp >= cut)
					print 'Resampling from', len(ok), 'good walkers'
					# Sample another walker
					J = np.random.randint(len(ok), size=len(I))
					lnp0 = lnp[I]
					lnp1 = lnp[J]
					for i,j in zip(I,J):
						pp[i,:] = emcee.EnsembleSampler.sampleBall(pp[j,:], psteps, 1)
					lnp2 = mp.map(tractor, pp[I])
					#print 'lnp0', lnp0
					#print 'lnp1', lnp1
					#print 'lnp2', lnp2
					print 'dlnps', ', '.join(['%.1f' % d for d in lnp2 - np.max(lnp)])
					lnp[I] = lnp2

		tractor.setCatalog(allsources)
		return dict(tractor=tractor, allp3=allp, pp3=pp, psteps3=psteps, Ibright3=Ibright)


	def stage04old(tractor=None, mp=None, steps=None, pp3=None, psteps3=None,
				Ibright3=None, **kwargs):
		print 'Tractor:', tractor
		tractor.mp = mp
		tractor.freezeParam('images')
		tractor.catalog.thawParamsRecursive('*')

		Ibright = Ibright3
		allsources = tractor.getCatalog()
		brightcat = [allsources[i] for i in Ibright]
		#brightcat,nil = cut_bright(allsources, magcut=23)
		tractor.setCatalog(brightcat)
		print ' Cut to:', tractor.getCatalog()

		pp = pp3
		#if psteps3 is None:
		#	psteps = np.std(pp, axis=0)
		#else:
		psteps = psteps3

		lnp = mp.map(tractor, pp)
		ibest = np.argmax(lnp)
		step = 100
		plots(tractor, ['modsum', 'chisum', 'modbest', 'chibest'],
			  step, pp=pp, ibest=ibest, **plotsa)

		pnames = np.array(tractor.getParamNames())
		st = np.std(pp, axis=0)
		mn = np.mean(pp, axis=0)
		print 'Params:'
		for nm,pmn,pst in zip(pnames, mn, st):
			print '  ', nm, 'mean', pmn, 'std', pst


	def optsourcestogether(tractor, step0):
		step = step0
		alllnp = []
		while True:
			print 'Run optimization step', step
			t0 = Time()
			dlnp,X,alpha = tractor.opt2(alphas=[0.01, 0.125, 0.25, 0.5, 1., 2., 4.])
			t_opt = (Time() - t0)
			print 'alpha', alpha
			print 'Optimization took', t_opt, 'sec'
			lnp0 = tractor.getLogProb()
			print 'Lnprob', lnp0
			alllnp.append([lnp0])
			if True:
				pp = np.array([tractor.getParams()])
				ibest = 0
				plots(tractor,
					  ['modbest', 'chibest', 'lnps'],
					  step, pp=pp, ibest=ibest, alllnp=alllnp, **plotsa)
			step += 1
			if alpha == 0.:
				break
		return step, alllnp

	def optsourcesseparate(tractor, step0, plotmod, plotsa):
		step = step0 - 1
		tractor.catalog.freezeAllParams()
		I = np.argsort([src.getBrightness().i for src in tractor.catalog])

		allsources = tractor.catalog

		pool_stats()

		alllnp = []
		for j,srci in enumerate(I):
			srci = int(srci)
			print 'source', j, 'of', len(I), ', srci', srci
			tractor.catalog.thawParam(srci)
			print tractor.numberOfParams(), 'active parameters'
			for nm in tractor.getParamNames():
				print '  ', nm
			print 'Source:', tractor.catalog[srci]

			# Here we subtract the other models from each image.
			# We could instead keep a table of model patches,
			# but this is not the bottleneck at the moment...
			tt0 = Time()
			others = tractor.catalog[0:srci] + tractor.catalog[srci+1:]
			origims = []
			for im in tractor.images:
				origims.append(im.data)
				sub = im.data.copy()
				sub -= tractor.getModelImage(im, others, sky=False)
				im.data = sub
			tractor.catalog = Catalog(allsources[srci])
			tpre = Time()-tt0
			print 'Removing other sources:', tpre
			src = allsources[srci]

			tt0 = Time()
			p0 = tractor.catalog.getParams()
			while True:
				step += 1
				print 'Run optimization step', step
				t0 = Time()
				dlnp,X,alpha = tractor.opt2(alphas=[0.01, 0.125, 0.25, 0.5, 1., 2., 4.])
				t_opt = (Time() - t0)
				print 'alpha', alpha
				print 'Optimization took', t_opt, 'sec'
				print src
				lnp0 = tractor.getLogProb()
				print 'Lnprob', lnp0
				alllnp.append([lnp0])
				if step % plotmod == 0:
					print 'Plots...'
					pp = np.array([tractor.getParams()])
					ibest = 0
					plots(tractor,
						  ['modbest', 'chibest', 'lnps'],
						  step, pp=pp, ibest=ibest, alllnp=alllnp, **plotsa)
					print 'Done plots.'
				if alpha == 0.:
					break
			print 'removing other sources:', Time()-tt0

			tractor.catalog = allsources
			for im,dat in zip(tractor.images, origims):
				im.data = dat

			tractor.catalog.freezeParam(srci)

			pool_stats()

		return step, alllnp


	# stage 3 replacement: "quick" fit of bright sources to one CFHT image
	def stage03(tractor=None, mp=None, steps=None, **kwargs):
		print 'Tractor:', tractor
		tractor.mp = mp
		tractor.freezeParam('images')
		tractor.catalog.thawParamsRecursive('*')
		params0 = np.array(tractor.getParams()).copy()
		allsources = tractor.getCatalog()
		brightcat,Ibright = cut_bright(allsources, magcut=23)
		tractor.setCatalog(brightcat)
		bparams0 = np.array(tractor.getParams()).copy()
		allimages = tractor.getImages()
		tractor.setImages(Images(allimages[0]))
		print ' Cut to:', tractor

		plotims = [0,]
		plotsa = dict(imis=plotims, mp=mp)

		alllnp,step = optsourcestogether(tractor, 0)

		step, alllnp2 = optsourcesseparate(tractor, step, 10, plotsa)
		alllnp += alllnp2

		tractor.catalog.thawParamsRecursive('*')
		bparams1 = np.array(tractor.getParams()).copy()
		tractor.setCatalog(allsources)
		tractor.setImages(allimages)
		params1 = np.array(tractor.getParams()).copy()
		#print 'dparams for bright sources:', bparams1 - bparams0
		#print 'dparams for all sources:', params1 - params0
		return dict(tractor=tractor, alllnp3=alllnp, Ibright3=Ibright)


	def stage04(tractor=None, mp=None, steps=None, alllnp3=None, Ibright3=None,
				**kwargs):
		print 'Tractor:', tractor
		tractor.mp = mp
		tractor.freezeParam('images')
		tractor.catalog.thawParamsRecursive('*')
		params0 = np.array(tractor.getParams()).copy()
		allsources = tractor.getCatalog()
		allimages = tractor.getImages()

		tractor.setImages(Images(allimages[0]))
		print ' Cut to:', tractor
		plotims = [0,]
		plotsa = dict(imis=plotims, mp=mp)

		step = 200-1
		step, alllnp = optsourcestogether(tractor, step)

		step, alllnp2 = optsourcesseparate(tractor, step, 10, plotsa)
		alllnp += alllnp2

		tractor.catalog.thawParamsRecursive('*')
		tractor.setImages(allimages)
		params1 = np.array(tractor.getParams()).copy()
		return dict(tractor=tractor, alllnp3=alllnp3, Ibright3=Ibright3,
					alllnp4=alllnp)

	def stage05(tractor=None, mp=None, steps=None,
				**kwargs):
		print 'Tractor:', tractor
		tractor.mp = mp
		tractor.freezeParam('images')
		tractor.catalog.thawParamsRecursive('*')
		tractor.catalog.freezeParamsRecursive('g', 'r', 'i')

		allimages = tractor.getImages()
		tractor.setImages(Images(*[im for im in allimages if im.name.startswith('CFHT')]))
		print ' Cut to:', tractor
		plotims = [0,]
		plotsa = dict(imis=plotims, mp=mp)

		step = 5000
		step, alllnp = optsourcestogether(tractor, step)
		step, alllnp2 = optsourcesseparate(tractor, step, 10, plotsa)
		alllnp += alllnp2

		tractor.catalog.thawParamsRecursive('*')
		return dict(tractor=tractor, alllnp5=alllnp)
		
	def stage06():
		p0 = np.array(tractor.getParams())
		pnames = np.array(tractor.getParamNames())

		ndim = len(p0)
		nw = 32

		sampler = emcee.EnsembleSampler(nw, ndim, tractor, pool = mp.pool,
										live_dangerously=True)
		mhsampler = emcee.EnsembleSampler(nw, ndim, tractor, pool = mp.pool,
										  live_dangerously=True)

		# Scale step sizes until we get small lnp changes
		stepscale = 1e-7
		psteps = stepscale * np.array(tractor.getStepSizes())
		while True:
			pp = emcee.EnsembleSampler.sampleBall(p0, psteps, nw)
			# Put one walker at the nominal position.
			pp[0,:] = p0
			lnp = np.array(mp.map(tractor, pp))
			dlnp = lnp - np.max(lnp)
			print 'dlnp min', np.min(dlnp), 'median', np.median(dlnp)
			if np.median(dlnp) > -10:
				break
			psteps *= 0.1
			stepscale *= 0.1

		stepscales = np.zeros_like(psteps) + stepscale

		rstate = None
		alllnp = []
		allp = []
		for step in range(1, 201):
			allp.append(pp.copy())
			alllnp.append(lnp.copy())
			if step % 10 == 0:
				ibest = np.argmax(lnp)
				plots(tractor, #['modsum', 'chisum', 'modbest', 'chibest', 'lnps'],
					  ['modbest', 'chibest', 'lnps'],
					  step, pp=pp, ibest=ibest, alllnp=alllnp, **plotsa)
			print 'Run MCMC step', step
			kwargs = dict(storechain=False)
			# Alternate 5 steps of stretch move, 5 steps of MH.
			t0 = Time()
			if step % 10 in [4, 9]:
				# Resample walkers that are doing badly
				bestlnp = np.max(lnp)
				dlnp = lnp - bestlnp
				cut = -20
				I = np.flatnonzero(dlnp < cut)
				print len(I), 'walkers have lnprob more than', -cut, 'worse than the best'
				if len(I):
					ok = np.flatnonzero(dlnp >= cut)
					print 'Resampling from', len(ok), 'good walkers'
					# Sample another walker
					J = ok[np.random.randint(len(ok), size=len(I))]
					lnp0 = lnp[I]
					lnp1 = lnp[J]
					print 'J', J.shape, J
					#print 'lnp0', lnp0.shape, lnp0
					#print 'lnp1', lnp1.shape, lnp1
					#print 'pp[J,:]', pp[J,:].shape
					#print 'psteps', psteps.shape
					#print 'rand', np.random.normal(size=(len(J),len(psteps))).shape
					ppnew = pp[J,:] + psteps * np.random.normal(size=(len(J),len(psteps)))
					#print 'ppnew', ppnew.shape
					lnp2 = np.array(mp.map(tractor, ppnew))
					#print 'lnp2', lnp2.shape, lnp2
					print 'dlnps', ', '.join(['%.1f' % d for d in lnp2 - np.max(lnp)])
					# M-H acceptance rule (from original position, not resampled)
					acc = emcee.EnsembleSampler.mh_accept(lnp0, lnp2)
					dlnp = lnp2[acc] - lnp[I[acc]]
					lnp[I[acc]] = lnp2[acc]
					pp[I[acc],:] = ppnew[acc,:]
					print 'Accepted', sum(acc), 'resamplings'
					print '  with dlnp mean', np.mean(dlnp), 'median', np.median(dlnp)
					# FIXME: Should record the acceptance rate of this...

			elif step % 10 >= 5:
				print 'Using MH proposal'
				kwargs['mh_proposal'] = emcee.MH_proposal_axisaligned(psteps)
				pp,lnp,rstate = mhsampler.run_mcmc(pp, 1, lnprob0=lnp, rstate0=rstate, **kwargs)
				print 'Running acceptance fraction: MH'#, mhsampler.acceptance_fraction
				print 'after', mhsampler.iterations, 'iterations'
				print 'mean', np.mean(mhsampler.acceptance_fraction)
			else:
				pp,lnp,rstate = sampler.run_mcmc(pp, 1, lnprob0=lnp, rstate0=rstate, **kwargs)
				print 'Running acceptance fraction: emcee'#, sampler.acceptance_fraction
				print 'after', sampler.iterations, 'iterations'
				print 'mean', np.mean(sampler.acceptance_fraction)
			t_mcmc = (Time() - t0)
			print 'Best lnprob:', np.max(lnp)
			print 'dlnprobs:', ', '.join(['%.1f' % d for d in lnp - np.max(lnp)])
			print 'MCMC took', t_mcmc, 'sec'

			# Tweak step sizes...
			print 'Walker stdevs / psteps:'
			st = np.std(pp, axis=0)
			f = st / np.abs(psteps)
			print '  median', np.median(f)
			print '  range', np.min(f), np.max(f)
			if step % 10 == 9:
				# After this batch of MH updates, tweak step sizes.
				acc = np.mean(mhsampler.acceptance_fraction)
				tweak = 2.
				if acc < 0.33:
					psteps /= tweak
					stepscales /= tweak
					print 'Acceptance rate too low: decreasing step sizes'
				elif acc > 0.66:
					psteps *= tweak
					stepscales *= tweak
					print 'Acceptance rate too high: increasing step sizes'
				print 'log-mean step scales', np.exp(np.mean(np.log(stepscales)))

			# # Note that this is per-parameter.
			# mx = 1.2
			# tweak = np.clip(f, 1./mx, mx)
			# psteps *= tweak
			# print 'After tweaking:'
			# f = st / np.abs(psteps)
			# print '  median', np.median(f)
			# print '  range', np.min(f), np.max(f)
		tractor.setCatalog(allsources)
		tractor.setImages(allimages)
		print 'Checking all-image, all-source logprob...'
		params1 = tractor.getParams()
		print 'Getting initial logprob...'
		tractor.setParams(params0)
		alllnp0 = tractor.getLogProb()
		print 'Initial log-prob (all images, all sources)', alllnp0
		print 'Getting final logprob...'
		tractor.setParams(params1)
		alllnp1 = tractor.getLogProb()
		print 'Initial log-prob (all images, all sources)', alllnp0
		print 'Final   log-prob (all images, all sources)', alllnp1
		return dict(tractor=tractor, allp3=allp, pp3=pp, psteps3=psteps, Ibright3=Ibright)
		

	def runstage(stage):
		print 'Runstage', stage
		pfn = 'tractor%02i.pickle' % stage
		if os.path.exists(pfn):
			if stage in opt.force:
				print 'Ignoring pickle', pfn, 'and forcing stage', stage
			else:
				print 'Reading pickle', pfn
				R = unpickle_from_file(pfn)
				return R
		if stage > 0:
			# Get prereqs
			P = runstage(stage-1)
		else:
			P = {}
		print 'Running stage', stage
		#F = locals()['stage%02i' % stage]
		#F = globals()['stage%02i' % stage]
		ss = { 0: stage00, 1: stage01, 2: stage02, 3: stage03, 4: stage04,
			   5: stage05, 6: stage06
			   }
		F = ss[stage]
		P.update(mp=mp)
		R = F(**P)
		print 'Saving pickle', pfn
		pickle_to_file(R, pfn)
		return R

	runstage(opt.stage)

	sys.exit(0)

	for x in []:
		#if False and step % 2 == 0:
		if True:
			print 'Run optimization step', step
			if len(pp) > 1:
				# print 'param shape', pp.shape
				stdev = np.std(pp, axis=0)
				print 'stdev', stdev
				steps = stdev
				mn = np.mean(pp, axis=0)
				print 'mean', mn
				tractor.setParams(mn)
			else:
				tractor.setParams(pp[0])
			t0 = Time()
			# tractor.optimizeCatalogAtFixedComplexityStep()
			tractor.opt2()
			t_opt = (Time() - t0)
			print 'Optimization took', t_opt, 'sec'
			pp = np.array([tractor.getParams()])
			lnp0 = tractor.getLogProb()
			print 'Lnprob', lnp0

if __name__ == '__main__':
	main()
