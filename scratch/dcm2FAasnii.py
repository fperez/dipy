from dipy.io import dicomreaders as dcm
import nibabel as ni
import numpy as np
from dipy.core import stensor as sten


dname='/home/eg309/Data/Eleftherios/Series_003_CBU_DTI_64D_iso_1000'
faname='/tmp/FA.nii'

data,affine,bvals,gradients=dcm.read_mosaic_dwi_dir(dname)

stl=sten.STensorL(bvals,gradients)

stl.fit(data)

stl.tensors
FA=stl.fa


img=ni.Nifti1Image(FA,affine)

ni.save(img,faname)

