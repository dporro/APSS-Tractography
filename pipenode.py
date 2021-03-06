# -*- coding: utf-8 -*-

"""
Module implementing the main sequence of pipeline analysis to process
diffusion MRI designed according to the requirements from APSS

Copyright (c) 2014, Fondazione Bruno Kessler
Distributed under the BSD 3-clause license. See COPYING.txt.
"""

import os
import sys
import glob
import pickle
import numpy as np
import nibabel as nib
from subprocess import Popen, PIPE
import dipy.reconst.dti as dti
from dipy.reconst.csdeconv import ConstrainedSphericalDeconvModel, auto_response
from dipy.align.aniso2iso import resample
from dipy.core.gradients import gradient_table
from dipy.io.dpy import Dpy
from dipy.data import get_sphere
from dipy.tracking.eudx import EuDX
from dipy.tracking.metrics import length
from dipy.tracking.distances import bundles_distances_mam
from dissimilarity_common import compute_dissimilarity
from parameters import *


def pipe(cmd, print_sto=True, print_ste=True):
    """Open a pipe to a subprocess where execute an external command.
    """
    p = Popen(cmd, shell=True, stdout=PIPE, stderr=PIPE)
    sto = p.stdout.readlines()
    ste = p.stderr.readlines()
    if print_sto :
        print(sto)
    if print_ste :
        print(ste)

def dcm2nii(dname, outdir, filt='*.dcm', options='-d n -g n -i n -o'):
    cmd = 'dcm2nii ' + options + ' ' + outdir + ' ' + dname
    pipe(cmd, print_sto=False, print_ste=False)


def eddy_correct(in_nii, out_nii, ref=0):
    cmd = 'eddy_correct ' + in_nii + ' ' + out_nii + ' ' + str(ref)
    pipe(cmd, print_sto=False, print_ste=False)


def bet(in_nii, out_nii, options=' -F -f .2 -g 0'):
    cmd = 'bet ' + in_nii + ' ' + out_nii + options
    pipe(cmd, print_sto=False, print_ste=False)


def dicom_to_nifti(src_dir, out_dir, subj_name, tag, opt=par_dcm2nii_options):

    if src_dir is not None and out_dir is not None:
        old_file = os.path.join(out_dir, subj_name + '_' + tag + '.nii')
        if os.path.exists(old_file): os.remove(old_file)
        old_file = os.path.join(out_dir, subj_name + '.bval')
        if os.path.exists(old_file): os.remove(old_file)
        old_file = os.path.join(out_dir, subj_name + '.bvec')
        if os.path.exists(old_file): os.remove(old_file)

    try:
        glob.glob(os.path.join(src_dir, '*.dcm'))[0]
        
    except IndexError:
        print "FAIL: dcm2nii - FILE: *.dcm not found"
        sys.exit()
 
    cmd = 'dcm2nii ' + opt + ' ' + out_dir + ' ' + src_dir
    pipe(cmd, print_sto=False, print_ste=False)
    all_file = glob.glob(os.path.join(out_dir, '*.nii'))
    new_file = min(all_file, key = os.path.getctime)
    del_file = os.path.basename(new_file)
    del_file = del_file.strip('co, o, .nii, .bval, .bvec')
    if tag == 'mri':
        old_file = os.path.join(out_dir, 'co' + del_file + '.nii')
        out_file = os.path.join(out_dir, subj_name + '_' + tag + '.nii')
        if os.path.exists(old_file):               
            os.rename(old_file, out_file)        
        old_file = os.path.join(out_dir, 'o' + del_file + '.nii')
        if os.path.exists(old_file): os.remove(old_file)
        old_file = os.path.join(out_dir, del_file + '.nii')
        if os.path.exists(old_file): os.remove(old_file)
    if tag == 'dmri':
        old_file = os.path.join(out_dir, del_file + '.nii')
        out_file = os.path.join(out_dir, subj_name + '_' + tag + '.nii')
        if os.path.exists(old_file):               
            os.rename(old_file, out_file)
        old_file = os.path.join(out_dir, del_file + '.bval')
        out_file = os.path.join(out_dir, subj_name + '.bval')
        if os.path.exists(old_file):               
            os.rename(old_file, out_file)
        old_file = os.path.join(out_dir, del_file + '.bvec')
        out_file = os.path.join(out_dir, subj_name + '.bvec')
        if os.path.exists(old_file):               
            os.rename(old_file, out_file)


def brain_extraction(src_bet, out_dir, subj_name, tag):

    try:
        out_bet_file = os.path.join(out_dir, subj_name + par_bet_suffix)
        if os.path.isdir(src_bet):
            bet_file = [f for f in os.listdir(src_bet) 
                        if f.endswith(subj_name + '_' + tag + '.nii')][0]
        src_bet_file = os.path.join(src_bet, bet_file)
        cmd = 'bet ' + src_bet_file + ' ' + out_bet_file + par_bet_options
        pipe(cmd, print_sto=False, print_ste=False)
    except:
        print "FAIL: bet - File: %s" % src_bet_file
        sys.exit()


def eddy_current_correction(src_ecc_dir, out_ecc_dir, subj_name):

    try:
        src_ecc_file = os.path.join(src_ecc_dir, subj_name + par_bet_suffix)
        out_ecc_file = os.path.join(out_ecc_dir, subj_name + par_ecc_suffix)
        if src_ecc_file is not None and out_ecc_file is not None:
            cmd = 'eddy_correct ' + src_ecc_file + ' ' + out_ecc_file + \
                  ' ' + str(par_ecc_ref)
            pipe(cmd, print_sto=False, print_ste=False)
    except:
        print "FAIL: eddy_correct - File: %s" % src_ecc_file
        sys.exit()


def rescaling_isotropic_voxel(src_iso_dir, out_iso_dir, subj_name):

    try:
        src_iso_file = os.path.join(src_iso_dir, subj_name + par_ecc_suffix)
        out_iso_file = os.path.join(out_iso_dir, subj_name + par_iso_suffix)
        if src_iso_file is not None and out_iso_file is not None:
            src_img = nib.load(src_iso_file)
            src_data = src_img.get_data()
            src_affine = src_img.get_affine()
        src_iso_size = src_img.get_header().get_zooms()[:3]
        out_iso_size = par_iso_voxel_size
        data, affine = resample(src_data, src_affine, src_iso_size,out_iso_size)
        data_img = nib.Nifti1Image(data, affine)
        nib.save(data_img, out_iso_file)
    except:
        print "FAIL: isotropic rescaling - File: %s" % src_iso_file
        exit


def flirt_registration(src_flirt_dir, ref_flirt_dir, out_flirt_dir, aff_flirt_dir, subj_name):

    src_flirt_file = os.path.join(src_flirt_dir, subj_name + par_bet_suffix)
    ref_flirt_file = os.path.join(ref_flirt_dir, subj_name + par_iso_suffix)
    out_flirt_file = os.path.join(out_flirt_dir, subj_name + par_flirt_suffix)
    aff_flirt_file = os.path.join(aff_flirt_dir, subj_name + par_aff_suffix)
    pipe('flirt -in ' + src_flirt_file + ' -ref '+ ref_flirt_file +' -out '+ out_flirt_file +' -omat '+ aff_flirt_file +' -dof '+ str(par_flirt_dof))


def atlas_registration(ref_flirt_dir, out_flirt_dir, aff_flirt_dir, subj_name):
    
    try:
        fsl_dir = os.environ['FSLDIR']
        fsl_atlas_file = [os.path.join(dirpath, f)
            for dirpath, dirnames, files in os.walk(fsl_dir, followlinks=True)
            for f in files if f.endswith(par_atlas_file)][0]
    except IndexError:
        print "FAIL: atlas file not found - File: %s" % par_atlas_file
        sys.exit()

    ref_flirt_file = os.path.join(ref_flirt_dir, subj_name + par_iso_suffix)
    out_flirt_file = os.path.join(out_flirt_dir, subj_name + par_atlas_suffix)
    aff_flirt_file = os.path.join(aff_flirt_dir, subj_name + par_aff_suffix)
    pipe('flirt -in ' + fsl_atlas_file + ' -ref '+ ref_flirt_file +' -out '+ out_flirt_file +' -omat '+ aff_flirt_file +' -dof '+ str(par_atlas_dof) + ' -bins 256 -cost corratio -searchrx -90 90 -searchry -90 90 -searchrz -90 90 -dof 12  -interp trilinear')


def compute_reconstruction(src_dmri_dir, subj_name):

    src_dmri_file = os.path.join(src_dmri_dir, subj_name + par_iso_suffix)
    src_bval_file = src_dmri_dir +  [each for each in os.listdir(src_dmri_dir) if each.endswith('.bval')][0]
    src_bvec_file = src_dmri_dir +  [each for each in os.listdir(src_dmri_dir) if each.endswith('.bvec')][0]

    img = nib.load(src_dmri_file)
    bvals = np.loadtxt(src_bval_file)
    bvecs = np.loadtxt(src_bvec_file).T
    data = img.get_data()
    affine = img.get_affine()

    gradients = gradient_table(bvals,bvecs)
    tensor_model = dti.TensorModel(gradients)  
    tensors = tensor_model.fit(data)
    FA = dti.fractional_anisotropy(tensors.evals)
    FA[np.isnan(FA)] = 0
    Color_FA = dti.color_fa(FA, tensors.evecs)

    out_evecs_file = os.path.join(src_dmri_dir, subj_name + par_evecs_suffix)
    evecs_img = nib.Nifti1Image(tensors.evecs.astype(np.float32), affine)
    nib.save(evecs_img, out_evecs_file)

    out_fa_file = os.path.join(src_dmri_dir, subj_name + par_fa_suffix)
    fa_img = nib.Nifti1Image(FA.astype(np.float32), affine)
    nib.save(fa_img, out_fa_file)

    out_cfa_file = os.path.join(src_dmri_dir, subj_name + par_cfa_suffix)
    cfa_img = nib.Nifti1Image(np.array(255*Color_FA,'uint8'), affine)
    nib.save(cfa_img, out_cfa_file)


def compute_tracking(src_dti_dir, out_trk_dir, subj_name):

    # Loading FA and evecs data
    src_fa_file = os.path.join(src_dti_dir, subj_name + par_fa_suffix)
    fa_img = nib.load(src_fa_file)
    FA = fa_img.get_data()

    src_evecs_file = os.path.join(src_dti_dir, subj_name + par_evecs_suffix)
    evecs_img = nib.load(src_evecs_file)
    evecs = evecs_img.get_data()

    # Computation of streamlines
    sphere = get_sphere('symmetric724') 
    peak_indices = dti.quantize_evecs(evecs, sphere.vertices)
    streamlines = EuDX(FA.astype('f8'),
                       ind=peak_indices, 
                       seeds=par_eudx_seeds,
                       odf_vertices= sphere.vertices,
                       a_low=par_eudx_threshold)

    # Saving tractography
    voxel_size = fa_img.get_header().get_zooms()[:3]
    dims = FA.shape[:3]
    seed = par_eudx_seeds
    seed = "_%d%s" % (seed/10**6 if seed>10**5 else seed/10**3, 
                      'K' if seed < 1000000 else 'M')

    hdr = nib.trackvis.empty_header()
    hdr['voxel_size'] = voxel_size
    hdr['voxel_order'] = 'LAS'
    hdr['dim'] = dims
    strm = ((sl, None, None) for sl in streamlines 
            if length(sl) > par_trk_min and length(sl) < par_trk_max)
    out_trk_file = os.path.join(out_trk_dir, subj_name + seed + par_trk_suffix)
    nib.trackvis.write(out_trk_file, strm, hdr, points_space='voxel')    

    tracks = [track for track in streamlines]
    out_dipy_file = os.path.join(out_trk_dir,subj_name + seed + par_dipy_suffix)
    dpw = Dpy(out_dipy_file, 'w')
    dpw.write_tracks(tracks)
    dpw.close()


def tractome_preprocessing(src_trk_dir, subj_name):

    seeds = par_eudx_seeds
    par2fun={par_prototype_distance:bundles_distances_mam}
    prototype_distance=par2fun[par_prototype_distance]
    trk_basename = "%s_%d%s%s" % (subj_name,
                                  seeds/10**6 if seeds>10**5 else seeds/10**3, 
                                  'K' if seeds < 1000000 else 'M',
                                  par_trk_suffix)
    spa_basename = os.path.splitext(trk_basename)[0] + '.spa'
    src_trk_file = os.path.join(src_trk_dir, trk_basename)
    out_spa_dir = os.path.join(src_trk_dir, '.temp')
    if not os.path.exists(out_spa_dir):
        os.makedirs(out_spa_dir)
    out_spa_file = os.path.join(out_spa_dir, spa_basename)

    streams, hdr = nib.trackvis.read(src_trk_file, points_space='voxel')
    streamlines =  np.array([s[0] for s in streams], dtype=np.object)
    dissimilarity_matrix = compute_dissimilarity(streamlines, 
            prototype_distance, par_prototype_policy, par_prototype_num)

    info = {'dismatrix':dissimilarity_matrix,'nprot':par_prototype_num}
    pickle.dump(info, open(out_spa_file,'w+'), protocol=pickle.HIGHEST_PROTOCOL)


