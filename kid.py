#!/usr/bin/python

import numpy as np
import cffi
import libcloudphxx as libcl
import pdb

ffi = cffi.FFI()

# object storing super-droplet model state (to be initialised)
prtcls = False

# dictionary of simulation parameters
params = {
  "real_t" : np.float64,
  "backend" : libcl.lgrngn.backend_t.serial,
  "sd_conc" : 128.,
  "kappa" : .61,
  "meanr" : .04e-6,
  "gstdv" : 1.4,
  "n_tot" : 100e6
}

arrays = {}
dt, dx, dz = 0, 0, 0
first_timestep = True
last_diag = -1
opts = libcl.lgrngn.opts_t()
opts.sstp_cond = 1
opts.sstp_coal = 1
opts.cond = True
opts.coal = True
opts.adve = True
opts.sedi = True
opts.chem = False

def lognormal(lnr):
  from math import exp, log, sqrt, pi
  return params["n_tot"] * exp(
    -pow((lnr - log(params["meanr"])), 2) / 2 / pow(log(params["gstdv"]),2)
  ) / log(params["gstdv"]) / sqrt(2*pi);

def ptr2np(ptr, size_x, size_z):
  numpy_ar = np.frombuffer(
    ffi.buffer(ptr, size_x*size_z*np.dtype(params["real_t"]).itemsize),
    dtype=params["real_t"]
  ).reshape(size_x, size_z)
  return numpy_ar

def th_kid2dry(arr):
  return arr #TODO!

def th_dry2kid(arr):
  return arr #TODO!

def rho_kid2dry(arr):
  return arr #TODO!

def diagnostics(particles, it):
  print "  diagnostics", it
  pass

@ffi.callback("void(int, int, int, double*, double*, double*, double*, double*, double*, double*, double*, double*, double*, double*, double*)")
def micro_step(it_diag, size_z, size_x, th_ar, qv_ar, rhof_ar, rhoh_ar, 
               uf_ar, uh_ar, wf_ar, wh_ar, xf_ar, zf_ar, xh_ar, zh_ar):
  global prtcls, dt, dx, dz, first_timestep, last_diag

# superdroplets: initialisation (done only once)
  if first_timestep:
    print "initialisation!"

    arrx = ptr2np(xf_ar, size_x, 1)
    arrz = ptr2np(zf_ar, 1, size_z)

    dt = 1 #TODO                                                                     
    dx = arrx[1,0] - arrx[0,0] #TODO, assert?                            
    dz = arrz[0,1] - arrz[0,0] #TODO, assert?                            
    print "dx, dz", dx, dz

    opts_init = libcl.lgrngn.opts_init_t()
    opts_init.dt = dt
    #opts_init.dx, opts_init.dz = dx, dz #TODO wait for 3D interface
    opts_init.sd_conc = params["sd_conc"]
    opts_init.dry_distros = { params["kappa"] : lognormal }

    prtcls = libcl.lgrngn.factory(params["backend"], opts_init)
  
    # allocating arrays for those variables that are not ready to use
    # (i.e. either different size or value conversion needed)
    arrays["rhod"] = np.empty((1, size_z))
    arrays["theta_d"] = np.empty((size_x-2, size_z))
    arrays["rhod_Cx"] = np.empty((size_x-1, size_z))
    arrays["rhod_Cz"] = np.empty((size_x-2, size_z+1))
    
  # mapping local NumPy arrays to the Fortran data locations   
  arrays["qv"] = ptr2np(qv_ar, size_x, size_z)[1:-1, :]
  arrays["thetad"] = th_kid2dry(ptr2np(th_ar, size_x, size_z)[1:-1, :])
  arrays["rhod"] = rho_kid2dry(ptr2np(rhof_ar, 1, size_z)[:])

  arrays["rhod_Cx"] = ptr2np(uh_ar, size_x, size_z)[:-1, :]
  assert (arrays["rhod_Cx"][0,:] == arrays["rhod_Cx"][-1,:]).all()
  arrays["rhod_Cx"] *= arrays["rhod"] * dt / dx

  arrays["rhod_Cz"][:, 1:] = ptr2np(wh_ar, size_x, size_z)[1:-1, :] 
  arrays["rhod_Cz"][:, 0 ] = 0
  arrays["rhod_Cz"][:, 1:] *= ptr2np(rhoh_ar, 1, size_z) * dt / dz

  
  if first_timestep:
    prtcls.init(arrays["thetad"], arrays["qv"], arrays["rhod"]) 
    #TODO: call diagnostics for t=0

  # superdroplets: all what have to be done within a timestep
  print "stepping"
  prtcls.step_sync(opts, arrays["thetad"], arrays["qv"],  arrays["rhod"]) #TODO: courants...
  prtcls.step_async(opts)

  # updating Fortran theta array (not needed for qv)
  #ptr2np(th_ar, size_x, size_z)[1:-1, :] = th_dry2kid(arrays["thetad"])

  # diagnostics
  if last_diag < it_diag:
    diagnostics(prtcls, it_diag)
    last_diag = it_diag

  first_timestep = False
  
# C functions
ffi.cdef("void save_ptr(char*,void*);")

# Fortran functions
ffi.cdef("void __main_MOD_main_loop();")

lib = ffi.dlopen('KiD_SC_2D.so')

# storing pointers to Python functions
lib.save_ptr("/tmp/micro_step.ptr", micro_step)

# running Fortran stuff
# note: not using command line arguments, namelist name hardcoded in
#       kid_a_setup/namelists/SC_2D_input.nml 
lib.__main_MOD_main_loop()
