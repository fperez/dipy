#from enthought.mayavi import mlab
import numpy as np
from scipy.special import sph_harm, lpn
from copy import copy, deepcopy

def real_sph_harm(m, n, theta, phi):
    """
    Compute real spherical harmonics, where the real harmonic $Y^m_n$ is
    defined to be:
        Real($Y^m_n$) * sqrt(2) if m > 0
        $Y^m_n$                 if m == 0
        Imag($Y^m_n$) * sqrt(2) if m < 0
    
    This may take scalar or array arguments. The inputs will be broadcasted
    against each other.
    
    :Parameters:
      - `m` : int |m| <= n
        The order of the harmonic.
      - `n` : int >= 0
        The degree of the harmonic.
      - `theta` : float [0, 2*pi]
        The azimuthal (longitudinal) coordinate.
      - `phi` : float [0, pi]
        The polar (colatitudinal) coordinate.
    
    :Returns:
      - `y_mn` : real float
        The real harmonic $Y^m_n$ sampled at `theta` and `phi`.

    :See also:
        scipy.special.sph_harm
    """
    m = np.atleast_1d(m)
    # find where m is =,< or > 0 and broadcasts to the size of the output
    m_eq0,junk,junk,junk = np.broadcast_arrays(m == 0, n, theta, phi)
    m_gt0,junk,junk,junk = np.broadcast_arrays(m > 0, n, theta, phi)
    m_lt0,junk,junk,junk = np.broadcast_arrays(m < 0, n, theta, phi)

    sh = sph_harm(m, n, theta, phi)
    real_sh = np.empty(sh.shape, 'double')
    real_sh[m_eq0] = sh[m_eq0].real
    real_sh[m_gt0] = sh[m_gt0].real * np.sqrt(2)
    real_sh[m_lt0] = sh[m_lt0].imag * np.sqrt(2)
    return real_sh

def sph_harm_ind_list(sh_order):
    """
    Returns the degree (n) and order (m) of all the symmetric spherical
    harmonics of degree less then or equal it sh_order. The results, m_list
    and n_list are kx1 arrays, where k depends on sh_order. They can be
    passed to real_sph_harm.

    Parameters
    ----------
    sh_order : int
        even int > 0, max degree to return

    Returns
    -------
    m_list : array
        orders of even spherical harmonics
    n_list : array
        degrees of even spherical hormonics

    See also
    --------
    real_sph_harm
    """
    if sh_order % 2 != 0:
        raise ValueError('sh_order must be an even integer >= 0')
    
    n_range = np.arange(0, np.int(sh_order+1), 2)
    n_list = np.repeat(n_range, n_range*2+1)

    ncoef = (sh_order + 2)*(sh_order + 1)/2
    offset = 0
    m_list = np.empty(ncoef, 'int')
    for ii in n_range:
        m_list[offset:offset+2*ii+1] = np.arange(-ii, ii+1)
        offset = offset + 2*ii + 1

    # makes the arrays ncoef by 1, allows for easy broadcasting later in code
    n_list = n_list[..., np.newaxis]
    m_list = m_list[..., np.newaxis]
    return (m_list, n_list)

class ModelParams(object):
    
    def __init__(self, mask, data):
        mask = mask.astype('bool')
        self._imask = np.zeros(mask.shape, 'int32')
        indexes =  mask[mask].cumsum()
        self._imask[mask] = indexes
        self._imask -= 1

        if data.shape[0] == indexes[-1]:
            self._data = data
        else:
            raise ValueError('the number of data elements does not match mask')
    
    @property
    def mask(self):
        return self._imask >= 0

    @property
    def dtype(self):
        return self._data.dtype
    
    def _get_shape(self):
        return self._imask.shape

    def _set_shape(self, value):
        self._imask.shape = value

    shape = property(_get_shape, _set_shape, "Tuple of array dimensions")

    def copy(self):
        data = self._data[self._imask[self.mask]]
        return ModelParams(self.mask, data)

    def __getitem__(self, index):
        new_mp = copy(self)
        new_mp._imask = self._imask[index]
        return new_mp
    
    def __setitem__(self, index, values):
        imask = self._imask[index]
        self._data[imask[imask >= 0]] = values

    def __array__(self, dtype=None):
        if dtype == self.dtype:
            return self._data[self._imask[self.mask]]
        else:
            return self._data[self._imask[self.mask]].astype(dtype)

class ODF(object):

    def _getshape(self):
        return self._coef.shape[:-1]
    shape = property(_getshape, doc="Shape of ODF array")

    def _getndim(self):
        return self._coef.ndim-1
    ndim = property(_getndim, doc="Number of dimensions in ODF array")

    def __getitem__(self, index):
        if type(index) != type(()):
            index = (index,)
        if len(index) > self.ndim:
            raise IndexError('invalid index')
        for ii in index[:]:
            if ii is Ellipsis:
                index = index + (slice(None),)
                break
        new_odf = copy(self)
        new_odf._coef = self._coef[index]
        if new_odf._resid is not None:
            new_odf._resid = self._resid[index]
        return new_odf
    
    def __init__(self, data, sh_order, grad_table, b_values, keep_resid=False):
        if (sh_order % 2 != 0 or sh_order < 0 ):
            raise ValueError('sh_order must be an even integer >= 0')
        self.sh_order = sh_order
        dwi = b_values > 0
        self.ngrad = dwi.sum()

        theta = np.arctan2(grad_table[1, dwi], grad_table[0, dwi])
        phi = np.arccos(grad_table[2, dwi])

        m_list, n_list = sph_harm_ind_list(self.sh_order)
        if m_list.size > self.ngrad:
            raise ValueError('sh_order seems too high, there are only '+
            str(self.ngrad)+' diffusion weighted images in data')
        comp_mat = real_sph_harm(m_list, n_list, theta, phi)

        self.fit_matrix = np.linalg.pinv(comp_mat)
        legendre0, junk = lpn(self.sh_order, 0)
        funk_radon = legendre0[n_list]
        self.fit_matrix *= funk_radon.T

        self.b0 = data[..., np.logical_not(dwi)]
        self._coef = np.dot(data[..., dwi], self.fit_matrix)

        if keep_resid:
            unfit = comp_mat / funk_radon
            self._resid = data[..., dwi] - np.dot(self._coef, unfit)
        else:
            self._resid = None

    def evaluate_at(self, theta_e, phi_e):
        
        m_list, n_list = sph_harm_ind_list(self.sh_order)
        comp_mat = real_sph_harm(m_list, n_list, theta_e.flat[:],
                                 phi_e.flat[:])
        values = np.dot(self._coef, comp_mat)
        values.shape = self.shape + np.broadcast(theta_e,phi_e).shape
        return values

    def evaluate_boot(self, theta_e, phi_e, permute=None):
        m_list, n_list = sph_harm_ind_list(self.sh_order)
        comp_mat = real_sph_harm(m_list, n_list, theta_e.flat[:],
                                 phi_e.flat[:])
        if permute == None:
            permute = np.random.permutation(self.ngrad)
        values = np.dot(self._coef + np.dot(self._resid[..., permute],
                        self.fit_matrix), comp_mat)
        return values

