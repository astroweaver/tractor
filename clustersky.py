# http://vizier.u-strasbg.fr/cgi-bin/VizieR-2?-source=VII/110A

# Full RAJ2000 DEJ2000 ACO BMtype  Count  z  Rich  	Dclass  m10
# 1689	197.89	-1.37	1689	II-III:	228 	0.1810	4	6	17.6
# 2219	250.09	+46.69	2219	III	159 	 	3	6	17.4
# 2261	260.62	+32.15	2261	 	128 	 	2	6	17.4

# Abell 2219
# (250.08, 46.71)
# 1453 5 57 (dist: 5.29006 arcmin)
# -> ~ x 200-600, y 0-400
# python tractor-sdss-synth.py -r 1453 -c 5 -f 57 -b r --dr9 --roi 200 600 0 400

# Abell 2261
# python tractor-sdss-synth.py -r 2207 -c 5 -f 162 -b r --dr9

# Abell 1689
# python tractor-sdss-synth.py -r 1140 -c 6 -f 300 -b r --dr9 --roi 0 1000 600 1400
# -> WHOA, Photo is messed up there!

# Richest cluster (=5)
# Abell 665
# (127.69, 65.88)

# Brightest cluster (in SDSS footprint)
# Abell 426
# (incl NGC 1270)
# python tractor-sdss-synth.py -r 3628 -c 1 -f 103 -b i --dr9
# --> Photo's models are too bright!

# Next,
# Abell 1656
# RCF [(5115, 5, 150, 194.92231764240464, 27.884313738504037), (5087, 6, 274, 194.91114434965587, 28.095153527922157)]
# 	  aco (<type 'numpy.int16'>) 1656 dtype int16
# 	  bmtype (<type 'numpy.string_'>) II dtype |S2
# 	  count (<type 'numpy.int16'>) 106 dtype int16
# 	  dclass (<type 'numpy.uint8'>) 1 dtype uint8
# 	  dec (<type 'numpy.float64'>) 27.9807003863 dtype float64
# 	  m10 (<type 'numpy.float32'>) 13.5 dtype float32
# 	  ra (<type 'numpy.float64'>) 194.953047094 dtype float64
# 	  rich (<type 'numpy.uint8'>) 2 dtype uint8
# 	  z (<type 'numpy.float32'>) 0.0232 dtype float32
#
# python tractor-sdss-synth.py -r 5115 -c 5 -f 150 -b i --dr9
# python tractor-sdss-synth.py -r 5115 -c 5 -f 151 -b i --dr9
##### ^^^^ #### nice
# python tractor-sdss-synth.py -r 5115 -c 5 -f 151 -b i --dr9 --roi 1048 2048 0 1000

# Richness:
#   Group 0: 30-49 galaxies
#   Group 1: 50-79 galaxies
#   Group 2: 80-129 galaxies
#   Group 3: 130-199 galaxies
#   Group 4: 200-299 galaxies
#   Group 5: more than 299 galaxies

# Distance:  Abell divided the clusters into seven "distance groups" according to the magnitudes of their tenth brightest members:
#   Group 1: mag 13.3-14.0
#   Group 2: mag 14.1-14.8
#   Group 3: mag 14.9-15.6
#   Group 4: mag 15.7-16.4
#   Group 5: mag 16.5-17.2
#   Group 6: mag 17.3-18.0
#   Group 7: mag > 18.0

if __name__ == '__main__':
	import matplotlib
	matplotlib.use('Agg')
import numpy as np
import pylab as plt

from astrometry.util.fits import *
from astrometry.util.file import *
from astrometry.util.sdss_radec_to_rcf import *
from astrometry.util.plotutils import ArcsinhNormalize
import astrometry.libkd.spherematch as sm
from astrometry.sdss import *

from tractor.utils import *
from tractor import sdss as st
from tractor import *
from tractor.sdss_galaxy import *


def fp():
	band = 'i'

	run, camcol, field = 5115, 5, 151
	bands = [band]
	roi = (1048,2048, 0,1000)
	tim,tinf = st.get_tractor_image_dr9(run, camcol, field, band,
										roi=roi, nanomaggies=True)
	ima = dict(interpolation='nearest', origin='lower',
			   extent=roi)
	zr2 = tinf['sky'] + tinf['skysig'] * np.array([-3, 100])
	#imb = ima.copy()
	#imb.update(vmin=tim.zr[0], vmax=tim.zr[1])
	imc = ima.copy()
	imc.update(norm=ArcsinhNormalize(mean=tinf['sky'], 
									 std=tinf['skysig']),
				vmin=zr2[0], vmax=zr2[1])


	

	# Match spectra with Abell catalog
	T = fits_table('a1656-spectro.fits')

	IJ = []
	cats = []
	for step in [0, 12]:
		tractor = unpickle_from_file('clustersky-%02i.pickle' % step)
		cat = tractor.getCatalog()
		cat = [src for src in cat if src.getBrightness().getMag(band) < 20]
		cats.append(cat)
		rd = [src.getPosition() for src in cat]
		ra  = np.array([p.ra  for p in rd])
		dec = np.array([p.dec for p in rd])
		rad = 1./3600.
		I,J,d = sm.match_radec(T.ra, T.dec, ra, dec, rad,
							   nearest=True)
		print len(I), 'matches on RA,Dec'
		#print I, J
		IJ.append((I,J))

	(I1,J1),(I2,J2) = IJ
	assert(np.all(I1 == I2))
	cat1 = [cats[0][j] for j in J1]
	cat2 = [cats[1][j] for j in J2]
	m1 = np.array([src.getBrightness().getMag(band) for src in cat1])
	m2 = np.array([src.getBrightness().getMag(band) for src in cat2])

	ps = PlotSequence('fp')

	plt.clf()
	plt.plot(m1, m2, 'k.')
	plt.xlabel('SDSS i mag')
	plt.ylabel('Tractor i mag')
	ax = plt.axis()
	mn,mx = min(ax[0],ax[2]), max(ax[1],ax[3])
	plt.plot([mn,mx],[mn,mx], 'k-', alpha=0.5)
	plt.axis(ax)
	ps.savefig()

	plt.clf()
	plt.plot(m1, m2-m1, 'k.')
	plt.xlabel('SDSS i mag')
	plt.ylabel('(Tractor - SDSS) i mag')
	plt.axhline(0, color='k', alpha=0.5)
	ps.savefig()

	sdss = DR9()
	p = sdss.readPhotoObj(run, camcol, field)
	print 'PhotoObj:', p
	objs = p.getTable()
	# from tractor.sdss.get_tractor_sources
	x0,x1,y0,y1 = roi
	bandnum = band_index(band)
	x = objs.colc[:,bandnum]
	y = objs.rowc[:,bandnum]
	I = ((x >= x0) * (x < x1) * (y >= y0) * (y < y1))
	objs = objs[I]
	# Only deblended children.
	objs = objs[(objs.nchild == 0)]
	objs.about()
	I3,J3,d = sm.match_radec(T.ra, T.dec, objs.ra, objs.dec, rad,
							 nearest=True)
	print 'Got', len(I3), 'matches to photoObj'
	

	# FP
	for I,cat,nm in [(I1,cat1,'SDSS'),(I2,cat2,'Tractor')]:
		#
		m0 = np.array([src.getBrightness().getMag(band) for src in cat])
		wcs = tim.getWcs()
		x0,y0 = wcs.x0,wcs.y0
		#rd0 = [src.getPosition() for src in cat]
		xy0 = np.array([wcs.positionToPixel(src.getPosition())
						for src in cat])
		
		origI = I
		keep = []
		keepI = []
		#print 'Matched sources:'
		for i,src in zip(I,cat):
			#print '  ', src
			if type(src) is CompositeGalaxy:
				devflux = src.brightnessDev.getFlux(band)
				expflux = src.brightnessExp.getFlux(band)
				df = devflux / (devflux + expflux)
				print '  dev fraction', df
				if df > 0.8:
					keep.append(src)
					keepI.append(i)
			if type(src) in [DevGalaxy]:
				keep.append(src)
				keepI.append(i)
		I,cat = keepI,keep
		m1 = np.array([src.getBrightness().getMag(band) for src in cat])
		xy1 = np.array([wcs.positionToPixel(src.getPosition())
						for src in cat])

		plt.clf()
		plt.imshow(tim.getImage(), **imc)
		ax = plt.axis()
		plt.gray()
		plt.colorbar()
		p1 = plt.plot(xy0[:,0]+x0, xy0[:,1]+y0, 'o', mec='m', mfc='none',
					  ms=8, mew=1)
		p2 = plt.plot(xy1[:,0]+x0, xy1[:,1]+y0, 'o', mec='r', mfc='none',
					  ms=10, mew=2)
		plt.legend((p1[0],p2[0]), ('Spectro sources', 'deV profiles'))
		for (x,y),i in zip(xy0, origI):
			plt.text(x+x0, y+y0 + 20,
					 '%.03f' % T.z[i], color='r', size=8,
				ha='center', va='bottom')
		plt.axis(ax)
		plt.title(nm)
		ps.savefig()


		

def test1():
	ps = PlotSequence('abell')

	run, camcol, field = 5115, 5, 151
	band = 'i'
	bands = [band]
	roi = (1048,2048, 0,1000)

	tim,tinf = st.get_tractor_image_dr9(run, camcol, field, band,
										roi=roi, nanomaggies=True)
	srcs = st.get_tractor_sources_dr9(run, camcol, field, band,
		roi=roi, nanomaggies=True,
		bands=bands)

	mags = [src.getBrightness().getMag(band) for src in srcs]
	I = np.argsort(mags)
	print 'Brightest sources:'
	for i in I[:10]:
		print '  ', srcs[i]
	
	ima = dict(interpolation='nearest', origin='lower',
			   extent=roi)
	zr2 = tinf['sky'] + tinf['skysig'] * np.array([-3, 100])
	imb = ima.copy()
	imb.update(vmin=tim.zr[0], vmax=tim.zr[1])
	imc = ima.copy()
	#imc.update(vmin=zr2[0], vmax=zr2[1])
	imc.update(norm=ArcsinhNormalize(mean=tinf['sky'],
									 std=tinf['skysig']),
				vmin=zr2[0], vmax=zr2[1])
	plt.clf()
	plt.imshow(tim.getImage(), **imb)
	plt.gray()
	plt.colorbar()
	ps.savefig()

	T = fits_table('a1656-spectro.fits')
	wcs = tim.getWcs()
	x0,y0 = wcs.x0,wcs.y0
	print 'x0,y0', x0,y0
	xy = np.array([wcs.positionToPixel(RaDecPos(r,d))
				   for r,d in zip(T.ra, T.dec)])
	sxy = np.array([wcs.positionToPixel(src.getPosition())
					for src in srcs])
	sxy2 = sxy[I[:20]]
	sa = dict(mec='r', mfc='None', ms=8, mew=1, alpha=0.5)
	pa = dict(mec='b', mfc='None', ms=6, mew=1, alpha=0.5)
	
	ax = plt.axis()
	plt.plot(xy[:,0]+x0, xy[:,1]+y0, 'o', **sa)
	plt.plot(sxy2[:,0]+x0, sxy2[:,1]+y0, 's', **pa)
	plt.axis(ax)
	ps.savefig()
	
	plt.clf()
	plt.imshow(tim.getImage(), **imc)
	plt.colorbar()
	ps.savefig()

	ax = plt.axis()
	plt.plot(xy[:,0]+x0, xy[:,1]+y0, 'o', **sa)
	plt.plot(sxy2[:,0]+x0, sxy2[:,1]+y0, 's', **pa)
	for (x,y),z in zip(xy, T.z):
		plt.text(x+x0, y+y0, '%.3f'%z)

	plt.axis(ax)
	ps.savefig()

	tractor = Tractor([tim], srcs)

	pnum = 00
	pickle_to_file(tractor, 'clustersky-%02i.pickle' % pnum)
	pnum += 1
	
	print tractor

	sdss = DR9()
	fn = sdss.retrieve('frame', run, camcol, field, band)
	frame = sdss.readFrame(run, camcol, field, band, filename=fn)

	sky = st.get_sky_dr9(frame)

	print tinf
	
	plt.clf()
	plt.imshow(sky, interpolation='nearest', origin='lower')
	plt.colorbar()
	ps.savefig()

	x0,x1,y0,y1 = roi
	roislice = (slice(y0,y1), slice(x0,x1))

	sky = sky[roislice]

	z0,z1 = tim.zr
	mn = (sky.min() + sky.max()) / 2.
	d = (z1 - z0)
	
	plt.clf()
	plt.imshow(sky, vmin=mn - d/2, vmax=mn + d/2, **ima)
	plt.colorbar()
	ps.savefig()
	
	imchi1 = ima.copy()
	imchi1.update(vmin=-5, vmax=5)
	imchi2 = ima.copy()
	imchi2.update(vmin=-50, vmax=50)
	
	def plotmod():
		mod = tractor.getModelImage(0)
		chi = tractor.getChiImage(0)
		plt.clf()
		plt.imshow(mod, **imb)
		plt.gray()
		plt.colorbar()
		ps.savefig()
		plt.clf()
		plt.imshow(mod, **imc)
		plt.gray()
		plt.colorbar()
		ps.savefig()
		plt.clf()
		plt.imshow(chi, **imchi1)
		plt.gray()
		plt.colorbar()
		ps.savefig()
		plt.clf()
		plt.imshow(chi, **imchi2)
		plt.gray()
		plt.colorbar()
		ps.savefig()

	plotmod()
		
	tractor.freezeParam('images')

	tractor.catalog.freezeAllRecursive()
	tractor.catalog.thawPathsTo(band)
	print 'Params:'
	for nm in tractor.getParamNames():
		print nm

	j=0
	while True:
		print '-------------------------------------'
		print 'Optimizing flux step', j
		print '-------------------------------------'
		dlnp,X,alpha = tractor.optimize()
		print 'delta-logprob', dlnp
		nup = 0
		for src in tractor.getCatalog():
			for b in src.getBrightnesses():
				f = b.getFlux(band)
				if f < 0:
					#print 'Clamping flux', f, 'up to zero'
					nup += 1
					b.setFlux(band, 0.)
		print 'Clamped', nup, 'fluxes up to zero'
		if dlnp < 1:
			break
		j += 1
		plotmod()
		
		pickle_to_file(tractor, 'clustersky-%02i.pickle' % pnum)
		print 'Saved pickle', pnum
		pnum += 1
		
	
	# for src in tractor.getCatalog():
	# 	for b in src.getBrightnesses():
	# 		f = b.getFlux(band)
	# 		if f <= 0:
	# 			print 'src', src
	# find_clusters()

	tractor.catalog.thawAllRecursive()
	
	j=0
	while True:
		print '-------------------------------------'
		print 'Optimizing all, step', j
		print '-------------------------------------'
		dlnp,X,alpha = tractor.optimize()
		print 'delta-logprob', dlnp
		nup = 0
		for src in tractor.getCatalog():
			for b in src.getBrightnesses():
				f = b.getFlux(band)
				if f < 0:
					#print 'Clamping flux', f, 'up to zero'
					nup += 1
					b.setFlux(band, 0.)
		print 'Clamped', nup, 'fluxes up to zero'
		if dlnp < 1:
			break
		j += 1

		plotmod()

		pickle_to_file(tractor, 'clustersky-%02i.pickle' % pnum)
		print 'Saved pickle', pnum
		pnum += 1


		
	mags = []
	for src in tractor.getCatalog():
		mags.append(src.getBrightness().getMag(band))
	I = np.argsort(mags)
	for i in I:
		tractor.catalog.freezeAllBut(i)
		j = 1
		while True:
			print '-------------------------------------'
			print 'Optimizing source', i, 'step', j
			print '-------------------------------------'
			print tractor.catalog[i]
			dlnp,X,alpha = tractor.optimize()
			print 'delta-logprob', dlnp

			for b in tractor.catalog[i].getBrightnesses():
				f = b.getFlux(band)
				if f < 0:
					print 'Clamping flux', f, 'up to zero'
					b.setFlux(band, 0.)

			print tractor.catalog[i]
			print
			if dlnp < 1:
				break
			j += 1

		plotmod()
		tractor.catalog.thawAllParams()

	pickle_to_file(tractor, 'clustersky-%02i.pickle' % pnum)
	print 'Saved pickle', pnum
	pnum += 1
		
def test2():
	band = 'i'
	ps = PlotSequence('abell')
	
	ps.skipto(56)
	pnum = 13
	tractor = unpickle_from_file('clustersky-12.pickle')

	print tractor
	tim = tractor.getImage(0)
	rng = tim.zr[1]-tim.zr[0]
	# Magic!
	zr2 = (tim.zr[0], tim.zr[0] + 103./13.)

	ima = dict(interpolation='nearest', origin='lower')
	imb = ima.copy()
	imb.update(vmin=tim.zr[0], vmax=tim.zr[1])
	imc = ima.copy()
	imc.update(vmin=zr2[0], vmax=zr2[1])
	imchi1 = ima.copy()
	imchi1.update(vmin=-5, vmax=5)
	imchi2 = ima.copy()
	imchi2.update(vmin=-50, vmax=50)
	
	def plotmod():
		mod = tractor.getModelImage(0)
		chi = tractor.getChiImage(0)
		plt.clf()
		plt.imshow(mod, **imb)
		plt.gray()
		plt.colorbar()
		ps.savefig()
		plt.clf()
		plt.imshow(mod, **imc)
		plt.gray()
		plt.colorbar()
		ps.savefig()
		plt.clf()
		plt.imshow(chi, **imchi1)
		plt.gray()
		plt.colorbar()
		ps.savefig()
		plt.clf()
		plt.imshow(chi, **imchi2)
		plt.gray()
		plt.colorbar()
		ps.savefig()

	from tractor.splinesky import SplineSky

	H,W = tim.shape
	NX,NY = 10,10
	vals = np.zeros((NY,NX))
	XX = np.linspace(0, W, NX)
	YY = np.linspace(0, H, NY)
	tim.sky = SplineSky(XX, YY, vals)

	tractor.thawAllRecursive()
	tractor.images[0].freezeAllBut('sky')
	tractor.catalog.freezeAllRecursive()
	tractor.catalog.thawPathsTo(band)

	def plotsky():
		skyim = np.zeros(tim.shape)
		tim.sky.addTo(skyim)
		plt.clf()
		plt.imshow(skyim, **ima)
		plt.gray()
		plt.colorbar()
		plt.title('Spline sky model')
		ps.savefig()
		

	j=0
	while True:
		print '-------------------------------------'
		print 'Optimizing fluxes + sky step', j
		print '-------------------------------------'
		dlnp,X,alpha = tractor.optimize()
		print 'delta-logprob', dlnp
		nup = 0
		for src in tractor.getCatalog():
			for b in src.getBrightnesses():
				f = b.getFlux(band)
				if f < 0:
					#print 'Clamping flux', f, 'up to zero'
					nup += 1
					b.setFlux(band, 0.)
		print 'Clamped', nup, 'fluxes up to zero'
		if dlnp < 1:
			break
		j += 1
		plotmod()
		plotsky()
		
		pickle_to_file(tractor, 'clustersky-%02i.pickle' % pnum)
		print 'Saved pickle', pnum
		pnum += 1

		print 'Sky:', tim.sky
	

	tractor.catalog.thawAllRecursive()

	j=0
	while True:
		print '-------------------------------------'
		print 'Optimizing all sources + sky step', j
		print '-------------------------------------'
		dlnp,X,alpha = tractor.optimize()
		print 'delta-logprob', dlnp
		nup = 0
		for src in tractor.getCatalog():
			for b in src.getBrightnesses():
				f = b.getFlux(band)
				if f < 0:
					#print 'Clamping flux', f, 'up to zero'
					nup += 1
					b.setFlux(band, 0.)
		print 'Clamped', nup, 'fluxes up to zero'
		if dlnp < 1:
			break
		j += 1
		plotmod()
		plotsky()
		
		pickle_to_file(tractor, 'clustersky-%02i.pickle' % pnum)
		print 'Saved pickle', pnum
		pnum += 1

		print 'Sky:', tim.sky


	
	
def find():
	cmap = {'_RAJ2000':'ra', '_DEJ2000':'dec', 'ACOS':'aco'}
	T1 = fits_table('abell.fits', column_map=cmap)
	#T1.about()
	T2 = fits_table('abell2.fits', column_map=cmap)
	#T2.about()
	T3 = fits_table('abell3.fits', column_map=cmap)
	#T3.about()
	#T3.rename('acos', 'aco')
	T = merge_tables([T1, T2, T3])
	T.about()
	#T.rename('_raj2000', 'ra')
	#T.rename('_dec2000', 'dec')

	ps = PlotSequence('abell-b')

	for anum in [2151]:
		I = np.flatnonzero(T.aco == anum)
		print 'Abell', anum, ': found', len(I)
		Ti = T[I[0]]
		Ti.about()

		rcf = radec_to_sdss_rcf(Ti.ra, Ti.dec, contains=True,
								tablefn='dr9fields.fits')
		if len(rcf) == 0:
			print '-> Not in SDSS'
			continue
		print 'RCF', rcf
		for r,c,f,ra,dec in rcf:
			print 'http://skyservice.pha.jhu.edu/DR9/ImgCutout/getjpegcodec.aspx?R=%i&C=%i&F=%i&Z=50' % (r,c,f)
		
	return

	
	plt.clf()
	plt.hist(T.rich, bins=np.arange(-0.5,max(T.rich)+0.5))
	plt.xlabel('Richness')
	ps.savefig()

	T5 = T[T.rich == 5]
	print 'Richness 5:', len(T5)
	T5[0].about()

	#plt.clf()
	#plt.hist(T.dclass
	I = np.argsort(T.m10)
	Tm = T[I]
	print Tm.m10[:20]
	urls = []
	for Ti in Tm[:20]:
		print 'ACO', Ti.aco
		rcf = radec_to_sdss_rcf(Ti.ra, Ti.dec, contains=True,
								tablefn='dr9fields.fits')
		if len(rcf) == 0:
			continue
		print 'RCF', rcf
		Ti.about()
		run,camcol,field,nil,nil = rcf[0]
		
		getim = st.get_tractor_image_dr9
		getsrc = st.get_tractor_sources_dr9
		bandname = 'i'
		tim,tinf = getim(run, camcol, field, bandname)
		sources = getsrc(run, camcol, field, bandname)
		tractor = Tractor([tim], sources)
		mod = tractor.getModelImage(0)

		urls.append('http://skyserver.sdss3.org/dr8/en/tools/chart/navi.asp?ra=%f&dec=%f' % (Ti.ra, Ti.dec))
		
		plt.clf()
		plt.imshow(mod, interpolation='nearest', origin='lower',
				   vmin=tim.zr[0], vmax=tim.zr[1])
		plt.gray()
		ps.savefig()
		plt.clf()
		plt.imshow(tim.getImage(),
				   interpolation='nearest', origin='lower',
				   vmin=tim.zr[0], vmax=tim.zr[1])
		plt.gray()
		ps.savefig()

	print '\n'.join(urls)



def find_clusters(tractor, tim):
	# Find connected clusters of sources
	# [ (mask patch, [src,src]), ... ]
	dtype = np.int
	clusters = []
	for i,src in enumerate(tractor.getCatalog()):
		print 'Clustering source', i
		p = tractor.getModelPatch(tim, src)
		nz = p.getNonZeroMask()
		nz.patch = nz.patch.astype(dtype)
		#print '  nz vals:', np.unique(nz.patch)
		found = []
		for j,(mask, srcs) in enumerate(clusters):
			if not mask.hasNonzeroOverlapWith(nz):
				continue
			print 'Overlaps cluster', j
			found.append(j)
			#print '  Nonzero mask pixels:', len(np.flatnonzero(mask.patch))
			mask.set(mask.performArithmetic(nz, '__iadd__', otype=dtype))
			#print '  Nonzero mask pixels:', len(np.flatnonzero(mask.patch))
			mask.trimToNonZero()
			#print '  Nonzero mask pixels:', len(np.flatnonzero(mask.patch))
			print '  mask type', mask.patch.dtype
			srcs.append(src)
				
		if len(found) == 0:
			print 'Creating new cluster', len(clusters)
			clusters.append((nz, [src]))

		elif len(found) > 1:
			print 'Merging clusters', found
			m0,srcs0 = clusters[found[0]]
			for j in found[1:]:
				mi,srcsi = clusters[j]
				m0.set(m0.performArithmetic(mi, '__iadd__', otype=dtype))
				srcs0.extend(srcsi)
			for j in reversed(found[1:]):
				del clusters[j]
			print 'Now have', len(clusters), 'clusters'
			
	print 'Found', len(clusters), 'clusters'
	for i,(mask,srcs) in enumerate(clusters):
		n = len(np.flatnonzero(mask.patch))
		print 'Cluster', i, 'has', len(srcs), 'sources and', n, 'pixels'
		if n == 0:
			continue
		plt.clf()
		plt.imshow(np.sqrt(mask.patch),
				   interpolation='nearest', origin='lower',
				   extent=mask.getExtent(), vmin=0, vmax=sqrt(max(1, mask.patch.max())))
		ax = plt.axis()
		plt.gray()
		xy = np.array([tim.getWcs().positionToPixel(src.getPosition())
					   for src in srcs])
		plt.plot(xy[:,0], xy[:,1], 'r+')
		plt.axis(ax)
		plt.colorbar()
		ps.savefig()

	
if __name__ == '__main__':
	#find()
	fp()
	sys.exit(0)
	test1()

	if False:
		run, camcol, field = 5115, 5, 151
		band = 'i'
		sdss = DR9()
		fn = sdss.retrieve('idR', run, camcol, field, band)
		print 'Got', fn
		P = pyfits.open(fn)[0]
		from astrometry.util.fix_sdss_idr import fix_sdss_idr
		P = fix_sdss_idr(P)
		D = P.data
		plt.clf()
		plt.imshow(D, interpolation='nearest', origin='lower',
				   vmin=2070, vmax=2120)
		plt.gray()
		plt.colorbar()
		plt.savefig('idr.png')
	
	test2()

