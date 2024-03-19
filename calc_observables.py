import numpy as np
from astropy.io import fits
from scipy.interpolate import RegularGridInterpolator
import SelectData
import matplotlib.pyplot as plt


def perform_fft(mod_dir, img_dir, plotting=False, addinfo=False, fig_dir=None,
                log_plotv=False, disk_only=False):
    """
    Function that takes an MCFOST model image .fits file, performs Fast Fourier Transform (FFT) and
    returns scipy interpolator objects, allowing to calculate the associated interferometric observables
    at different (u, v) spatial frequencies. Options allow for diagnostic plots and extra info.
    Note: assumes a regular rectangular pixel grid
    """
    az, inc = 0, 0  # only one azimuthal/inc value in the .fits files to be loaded

    rad_to_mas = 206264806.2471  # radian to mili-arcsecond conversion
    mum_to_m = 1e-6  # micrometer to meter conversion

    # open the required fits file + get some header info
    hdul = fits.open(f'{mod_dir}/{img_dir}/RT.fits.gz')

    # read in the wavelength, pixelscale and 'window size' (e.g. size of axis images in radian)
    wave = hdul[0].header['WAVE']
    pixelscale_x = abs(hdul[0].header['CDELT1']) * np.pi / 180  # loaded in degrees, converted to radian
    pixelscale_y = abs(hdul[0].header['CDELT2']) * np.pi / 180
    num_pix_x = hdul[0].header['NAXIS1']  # number of pixels
    num_pix_y = hdul[0].header['NAXIS2']
    image_size_x = pixelscale_x * num_pix_x  # image size along 1 axis directly in radian
    image_size_y = pixelscale_y * num_pix_y

    img_array = hdul[0].data / wave
    img_array = np.flip(img_array, axis=3)  # flip y-array (to match numpy axis convention)

    img_tot = img_array[0, az, inc, :, :]
    img_star = img_array[4, az, inc, :, :]
    img_disk = (img_tot - img_star)

    if disk_only:
        img = img_disk / np.max(img_disk)
    else:
        img = img_tot / np.max(img_tot)

    # normalized fft
    ftot_lam = np.sum(img)
    img_fft_norm = np.fft.fftshift(np.fft.fft2(np.fft.fftshift(img))) / ftot_lam

    # extract squared visibilities and complex phases
    img_fft_norm_v2 = abs(img_fft_norm) ** 2
    img_fft_norm_phi = np.angle(img_fft_norm, deg=True)

    # extract info on the frequencies, note this is in units of 1/pixel
    # !!! NOTE: the first axis in a numpy array is the y-axis of the image, the second axis is the x-axis
    # !!! NOTE: we add a minus because the positive x- and y-axis convention in numpy
    # is the reverse of the interferometric one !!!

    w_x = -np.fft.fftshift(np.fft.fftfreq(img_fft_norm.shape[1]))  # also use fftshift so the 0 frequency can lie
    w_y = -np.fft.fftshift(np.fft.fftfreq(img_fft_norm.shape[0]))  # in the middle of the returned array

    # convert to uv-baseline units (i.e. 1st a conversion to 1/radian, then express in terms of baseline length
    # in MegaLambda). NOTE: strictly speaking we're expresing baseline 'length' as MegaLambda is a unit of length,
    # Note in OFITS file uv is not frequency, but u & v are baseline lengths (bad habit of community).
    # Conversion is straigthforward though. Baseline length u_x = 5 MLambda -> spatial_freq_x = 5e6 rad^-1.
    # Correspondingly, spatial_freq_x = 10e6 rad^-1 at Lambda = 1 micron -> projected baseline length
    # = 10e6 * 1 micron = 10 meter.

    uf = w_x / pixelscale_x  # spatial frequencies in units of 1/radian
    vf = w_y / pixelscale_y

    # make interpolator for V2, note we swap the axes of the FFT, so we can call on the interpolator
    # with a (u, v) tupple
    interp_v2 = RegularGridInterpolator((uf, vf), np.swapaxes(img_fft_norm_v2, 0, 1))
    # make interpolator for complex phase
    interp_phi = RegularGridInterpolator((uf, vf), np.swapaxes(img_fft_norm_phi, 0, 1))

    baseu = uf / 1e6  # Baseline length u in MegaLambda
    basev = vf / 1e6  # Baseline length v in MegaLambda

    step_baseu = abs(baseu[1] - baseu[0])  # retrieve the sampling steps in u baseline length
    step_basev = abs(basev[1] - basev[0])  # retrieve the sampling steps in v baseline length

    if plotting:
        # do some plotting
        fig, ax = plt.subplots(2, 3, figsize=(12, 8))
        color_map = 'inferno'

        # normalized intensity plotted in pixel scale
        # -------------------------------------------
        # also set the extent of the image when you plot it, take care that the number of pixels is even
        disk_plot = ax[0][0].imshow(img, cmap=color_map,
                                    extent=(num_pix_x / 2 + 0.5, -num_pix_x / 2 + 0.5,
                                            -num_pix_y / 2 + 0.5, num_pix_y / 2 + 0.5))
        fig.colorbar(disk_plot, ax=ax[0][0], label='$I/I_{max}$', fraction=0.046, pad=0.04)
        ax[0][0].set_title('Normalized disk intensity')
        ax[0][0].set_xlabel("E-W [pixel]")
        ax[0][0].set_ylabel("S-N [pixel]")
        ax[0][0].arrow(0.90, 0.80, -0.1, 0, color='white', transform=ax[0][0].transAxes,
                       length_includes_head=True, head_width=0.015)  # draw arrows to indicate direction
        ax[0][0].text(0.78, 0.83, "E", color='white', transform=ax[0][0].transAxes)
        ax[0][0].arrow(0.90, 0.80, 0, 0.1, color='white', transform=ax[0][0].transAxes,
                       length_includes_head=True, head_width=0.015)
        ax[0][0].text(0.92, 0.90, "N", color='white', transform=ax[0][0].transAxes)
        ax[0][0].axhline(y=0, lw=0.2, color='white')
        ax[0][0].axvline(x=0, lw=0.2, color='white')

        # squared visibility of the direct fourier transform in pixel scale
        # -------------------------------------------
        if log_plotv:
            v2plot = ax[0][1].imshow(np.log10(abs(img_fft_norm) ** 2), cmap=color_map,
                                     extent=(num_pix_x / 2 + 0.5, -num_pix_x / 2 + 0.5,
                                             -num_pix_y / 2 + 0.5, num_pix_y / 2 + 0.5))
            fig.colorbar(v2plot, ax=ax[0][1], label='$log_{10} V^2$', fraction=0.046, pad=0.04)
        else:
            v2plot = ax[0][1].imshow(abs(img_fft_norm) ** 2, cmap=color_map,
                                     extent=(num_pix_x / 2 + 0.5, -num_pix_x / 2 + 0.5,
                                             -num_pix_y / 2 + 0.5, num_pix_y / 2 + 0.5))
            fig.colorbar(v2plot, ax=ax[0][1], label='$V^2$', fraction=0.046, pad=0.04)
        ax[0][1].axhline(y=0, lw=0.2, color='black')
        ax[0][1].axvline(x=0, lw=0.2, color='black')

        ax[0][1].set_title('$V^2$')
        ax[0][1].set_xlabel(r"$\leftarrow u$ [1/pixel]")
        ax[0][1].set_ylabel(r"$v \rightarrow$ [1/pixel]")

        # complex phase of the direct fourier transform in pixel scale
        # -------------------------------------------
        phi_plot = ax[0][2].imshow(np.angle(img_fft_norm, deg=True), cmap=color_map,
                                   extent=(num_pix_x / 2 + 0.5, -num_pix_x / 2 + 0.5,
                                           -num_pix_y / 2 + 0.5, num_pix_y / 2 + 0.5))
        fig.colorbar(phi_plot, ax=ax[0][2], label=r'$\phi$ [$^\circ$]', fraction=0.046, pad=0.04)
        ax[0][2].axhline(y=0, lw=0.2, color='black')
        ax[0][2].axvline(x=0, lw=0.2, color='black')

        ax[0][2].set_title(r'Complex phase $\phi$')
        ax[0][2].set_xlabel(r"$\leftarrow u$ [1/pixel]")
        ax[0][2].set_ylabel(r"$v \rightarrow$ [1/pixel]")

        # normalized intensity plotted in angle scale
        # -------------------------------------------
        disk_plot = ax[1][0].imshow(img, cmap=color_map, aspect='auto',
                                    extent=((num_pix_x / 2) * pixelscale_x * rad_to_mas,
                                            (-num_pix_x / 2) * pixelscale_x * rad_to_mas,
                                            (-num_pix_y / 2) * pixelscale_y * rad_to_mas,
                                            (num_pix_y / 2) * pixelscale_y * rad_to_mas))
        fig.colorbar(disk_plot, ax=ax[1][0], label='$I/I_{max}$', fraction=0.046, pad=0.04)
        ax[1][0].set_aspect(num_pix_y / num_pix_x)
        ax[1][0].set_title('Normalized disk intensity')
        ax[1][0].set_xlabel("E-W [mas]")
        ax[1][0].set_ylabel("S-N [mas]")
        ax[1][0].arrow(0.90, 0.80, -0.1, 0, color='white', transform=ax[1][0].transAxes,
                       length_includes_head=True, head_width=0.015)  # draw arrows to indicate direction
        ax[1][0].text(0.78, 0.83, "E", color='white', transform=ax[1][0].transAxes)
        ax[1][0].arrow(0.90, 0.80, 0, 0.1, color='white', transform=ax[1][0].transAxes,
                       length_includes_head=True, head_width=0.015)
        ax[1][0].text(0.92, 0.90, "N", color='white', transform=ax[1][0].transAxes)
        ax[1][0].axhline(y=0, lw=0.2, color='white')
        ax[1][0].axvline(x=0, lw=0.2, color='white')

        # squared visibility of the direct fourier transform in MegaLambda (baseline length) scale
        # -------------------------------------------
        if log_plotv:
            v2plot = ax[1][1].imshow(np.log10(abs(img_fft_norm) ** 2), cmap=color_map,
                                     extent=((num_pix_x / 2 + 0.5) * step_baseu, (-num_pix_x / 2 + 0.5) * step_baseu,
                                             (-num_pix_y / 2 + 0.5) * step_basev, (num_pix_y / 2 + 0.5) * step_basev))
            fig.colorbar(v2plot, ax=ax[1][1], label='$log_{10} V^2$', fraction=0.046, pad=0.04)
        else:
            v2plot = ax[1][1].imshow(abs(img_fft_norm) ** 2, cmap=color_map,
                                     extent=((num_pix_x / 2 + 0.5) * step_baseu, (-num_pix_x / 2 + 0.5) * step_baseu,
                                             (-num_pix_y / 2 + 0.5) * step_basev, (num_pix_y / 2 + 0.5) * step_basev))
            fig.colorbar(v2plot, ax=ax[1][1], label='$V^2$', fraction=0.046, pad=0.04)
        ax[1][1].axhline(y=0, lw=0.2, color='black')
        ax[1][1].axvline(x=0, lw=0.2, color='black')

        ax[1][1].set_title('$V^2$')
        ax[1][1].set_xlabel(r"$\leftarrow B_u$ [$\mathrm{M \lambda}$]")
        ax[1][1].set_ylabel(r"$B_v \rightarrow$ [$\mathrm{M \lambda}$]")

        # complex phase of the direct fourier transform in MegaLambda (baseline length) scale
        # -------------------------------------------
        phi_plot = ax[1][2].imshow(np.angle(img_fft_norm, deg=True), cmap=color_map,
                                   extent=((num_pix_x / 2 + 0.5) * step_baseu, (-num_pix_x / 2 + 0.5) * step_baseu,
                                           (-num_pix_y / 2 + 0.5) * step_basev, (num_pix_y / 2 + 0.5) * step_basev))
        fig.colorbar(phi_plot, ax=ax[1][2], label=r'$\phi$ [$^\circ$]', fraction=0.046, pad=0.04)
        ax[1][2].axhline(y=0, lw=0.2, color='black')
        ax[1][2].axvline(x=0, lw=0.2, color='black')
        ax[1][2].set_title(r'Complex phase $\phi$')
        ax[1][2].set_xlabel(r"$\leftarrow B_u$ [$\mathrm{M \lambda}$]")
        ax[1][2].set_ylabel(r"$B_v \rightarrow$ [$\mathrm{M \lambda}$]")

        # draw lines/cuts along which we will plot some curves
        ax[1][1].plot(np.zeros_like(basev[1:int(num_pix_y / 2) + 1]), basev[1:int(num_pix_y / 2) + 1], c='g', lw=2,
                      ls='--')
        ax[1][1].plot(baseu[1:int(num_pix_x / 2) + 1], np.zeros_like(baseu[1:int(num_pix_x / 2) + 1]), c='b', lw=2)

        ax[1][2].plot(np.zeros_like(basev[1:int(num_pix_y / 2) + 1]), basev[1:int(num_pix_y / 2) + 1], c='g', lw=2,
                      ls='--')
        ax[1][2].plot(baseu[1:int(num_pix_x / 2) + 1], np.zeros_like(baseu[1:int(num_pix_x / 2) + 1]), c='b', lw=2)

        plt.tight_layout()

        if fig_dir is not None:
            plt.savefig(f"{fig_dir}/fft2d_maps_{wave}mum.png", dpi=300)

        # Some plots of specific cuts in frequency space
        fig2, ax2 = plt.subplots(2, 1, figsize=(6, 6))

        # Cuts of V^2 plot in function of baseline length
        # -------------------------------------------

        # note we cut away the point furthest along positive u-axis since it contains a strong artefact due to
        # the FFT algorithm, otherwise we move down to spatial frequency 0
        v2hor = abs(
            img_fft_norm[int(num_pix_y / 2), 1:int(num_pix_x / 2) + 1]) ** 2  # extract squared visibility along u-axis
        phi_hor = np.angle(img_fft_norm[int(num_pix_y / 2), 1:], deg=True)  # extract complex phase

        v2ver = abs(
            img_fft_norm[1:int(num_pix_y / 2) + 1, int(num_pix_x / 2)]) ** 2  # extract squared visibility along u-axis
        phi_basever = np.angle(img_fft_norm[1:, int(num_pix_x / 2)], deg=True)  # extract complex phase

        ax2[0].plot(baseu[1:int(num_pix_x / 2) + 1], v2hor, c='b', label="along u-axis", lw=0.7, zorder=1000)
        ax2[1].plot(baseu[1:], phi_hor, c='b', lw=0.7, zorder=1000)

        ax2[0].plot(basev[1:int(num_pix_y / 2) + 1], v2ver, c='g', label="along v-axis", lw=0.7, zorder=1000, ls='--')
        ax2[1].plot(basev[1:], phi_basever, c='g', lw=0.7, zorder=1000, ls='--')

        ax2[0].set_title('$V^2$ cuts')
        ax2[0].set_xlabel(r'$B$ [$\mathrm{M \lambda}$]')
        ax2[0].set_ylabel('$V^2$')
        ax2[0].axvline(x=0, c='k', lw=0.3, ls="-", zorder=0)
        if log_plotv:
            ax2[0].set_yscale("log")
            ax2[0].set_ylim(np.min(np.append(v2hor, v2ver)), 1.1)
        else:
            ax2[0].axhline(y=0, c='k', lw=0.3, ls="-", zorder=0)
            ax2[0].set_ylim(-0.1, 1.1)

        ax2[1].set_title(r'$\phi$ cuts')
        ax2[1].set_xlabel(r'$B$ [$\mathrm{M \lambda}$]')
        ax2[1].set_ylabel(r'$\phi$ [$^\circ$]')
        ax2[1].axvline(x=0, c='k', lw=0.3, ls="-", zorder=0)
        ax2[1].axhline(y=0, c='k', lw=0.3, ls="-", zorder=0)
        ax2[1].axhline(y=180, c='k', lw=0.3, ls="--", zorder=0)
        ax2[1].axhline(y=-180, c='k', lw=0.3, ls="--", zorder=0)

        ax2[0].legend()

        plt.tight_layout()

        if fig_dir is not None:
            plt.savefig(f"{fig_dir}/fft1d_cuts_{wave}mum.png", dpi=300)

    if addinfo:
        print("FREQUENCY INFORMATION IN PIXEL UNITS: \n" + "=====================================")
        print("Maximum frequency considered E-W [1/pixel]: " + str(np.max(w_x)))
        print("Maximum frequency considered S-N [1/pixel]: " + str(np.max(w_y)))
        print("This should equal the Nyquist frequency = 0.5 x 1/sampling_rate" +
              "(sampling_rate = 1 pixel in pixel units, = 1 pixelscale in physical units)")
        print("Spacing in frequency space E-W [1/pixel]: " + str(w_x[1] - w_x[0]))
        print("Spacing in frequency space South-North [1/pixel]: " + str(w_y[1] - w_y[0]))
        print("This should equal 1/window_size (i.e. = 1/(#pixels) in pixel units, " +
              "= 1/image_size in physical units)")
        print("===================================== \n")
        print("FREQUENCY INFORMATION IN ANGULAR UNITS: \n" + "=======================================")
        print("Pixel scale E-W [rad]: " + str(pixelscale_x))
        print("Pixel scale S-N [rad]: " + str(pixelscale_y))
        print("Image axes size E-W [rad]: " + str(image_size_x))
        print("Image axes size S-N [rad]: " + str(image_size_y) + "\n")
        print("Maximum frequency considered E-W [1/rad]: " + str(np.max(w_x) * 1 / pixelscale_x))
        print("Maximum frequency considered S-N [1/rad]: " + str(np.max(w_y) * 1 / pixelscale_y))
        print("Spacing in frequency space E-W [1/rad]: " + str(abs((w_x[1] - w_x[0]) * 1 / pixelscale_x)))
        print("Spacing in frequency space S-N [1/rad]: " + str(abs((w_y[1] - w_y[0]) * 1 / pixelscale_y)))
        print("-----------------------------------")
        print("Pixel scale E-W [mas]: " + str(pixelscale_x * rad_to_mas))  # 206264806.2471 mas in 1 rad
        print("Pixel scale S-N [mas]: " + str(pixelscale_y * rad_to_mas))
        print("Image axes size E-W [mas]: " + str(image_size_x * rad_to_mas))
        print("Image axes size S-N [mas]: " + str(image_size_y * rad_to_mas) + "\n")
        print("Maximum frequency considered E-W [1/mas]: " + str(np.max(w_x) * 1 / (pixelscale_x * rad_to_mas)))
        print(
            "Spacing in frequency space E-W [1/mas]: " + str(abs((w_x[1] - w_x[0]) * 1 / (pixelscale_x * rad_to_mas))))
        print("Maximum frequency considered S-N [1/mas]: " + str(np.max(w_y) * 1 / (pixelscale_y * rad_to_mas)))
        print(
            "Spacing in frequency space S-N [1/mas]: " + str(abs((w_y[1] - w_y[0]) * 1 / (pixelscale_y * rad_to_mas))))
        print("===================================== \n")
        print(r"FREQUENCY INFORMATION IN TERMS OF CORRESPONDING BASELINE LENGTH: " +
              "\n" + "===========================================================================")
        print("Maximum baseline resolvable under current pixel sampling E-W [Mlambda]: " +
              str((np.max(w_x) * 1 / pixelscale_x) / 1e6))
        print("Spacing in baseline length corresponding to frequency sampling E-W [Mlambda]: " +
              str(abs(((w_x[1] - w_x[0]) * 1 / pixelscale_x) / 1e6)))
        print("Maximum baseline resolvable under current pixel sampling S-N [Mlambda]: " +
              str((np.max(w_y) * 1 / pixelscale_y) / 1e6))
        print("Spacing in baseline length corresponding to frequency sampling S-N [Mlambda]: " +
              str(abs(((w_y[1] - w_y[0]) * 1 / pixelscale_y) / 1e6)))
        print("-----------------------------------")
        print("Maximum baseline resolvable under current pixel sampling E-W [m]: " +
              str(((np.max(w_x) * 1 / pixelscale_x) / 1e6) * 1e6 * wave * mum_to_m))
        print("Spacing in baseline length corresponding to frequency sampling E-W [m]: " +
              str(abs((((w_x[1] - w_x[0]) * 1 / pixelscale_x) / 1e6) * 1e6 * wave * mum_to_m)))
        print("Maximum baseline resolvable under current pixel sampling S-N [m]: " +
              str(((np.max(w_y) * 1 / pixelscale_y) / 1e6) * 1e6 * wave * mum_to_m))
        print("Spacing in baseline length corresponding to frequency sampling S-N [m]: " +
              str(abs((((w_y[1] - w_y[0]) * 1 / pixelscale_y) / 1e6) * 1e6 * wave * mum_to_m)))
        print("=========================================================================== \n")

    return interp_v2, interp_phi


def get_observation_data(data_dir, data_file, wavelim_lower=None, wavelim_upper=None):
    """
    Function to retrieve observation data from OIFITS files and return it as raveled numpy arrays in a dictionary.
    This is basically a wrapper around ReadOIFITS.py and SelectDate.py, but the raveled numpy arrays make things
    easier to calculate/interpolate using numpy/scipy. wave_1 and 2 are wavelength limits in meter to be applied.
    """
    oidata = SelectData.SelectData(data_dir=data_dir, data_file=data_file,
                                   wave_1=wavelim_lower / 1e6, wave_2=wavelim_upper / 1e6)

    obsvbs_dat = {}

    ufdat = []  # arrays to store all necessary variables in a 1d array
    vfdat = []
    wavedat = []
    v2dat = []
    v2err = []

    u1fdat = []
    v1fdat = []
    u2fdat = []
    v2fdat = []
    t3wavedat = []
    t3phidat = []
    t3phierr = []

    # get V2 data
    for vis2table in oidata.vis2:
        ufdat.extend(np.ravel(vis2table.uf))  # unravel the arrays to make them 1d
        vfdat.extend(np.ravel(vis2table.vf))
        wavedat.extend(np.ravel(vis2table.effwave))
        v2dat.extend(np.ravel(vis2table.vis2data))
        v2err.extend(np.ravel(vis2table.vis2err))

        # get phi_closure data
    for t3table in oidata.t3:
        # set uv coordinates (lengths) in 1/radian (spatial frequency) immediately
        u1fdat.extend(np.ravel(t3table.u1coord) / np.ravel(t3table.effwave))
        v1fdat.extend(np.ravel(t3table.v1coord) / np.ravel(t3table.effwave))
        u2fdat.extend(np.ravel(t3table.u2coord) / np.ravel(t3table.effwave))
        v2fdat.extend(np.ravel(t3table.v2coord) / np.ravel(t3table.effwave))
        t3wavedat.extend(np.ravel(t3table.effwave))
        t3phidat.extend(np.ravel(t3table.t3phi))
        t3phierr.extend(np.ravel(t3table.t3phierr))

    ufdat = np.array(ufdat)  # transfer into numpy arrays
    vfdat = np.array(vfdat)
    wavedat = np.array(wavedat)
    v2dat = np.array(v2dat)
    v2err = np.array(v2err)
    base = np.sqrt(ufdat ** 2 + vfdat ** 2) / 1e6  # uv baseline length in MegaLambda

    u1fdat = np.array(u1fdat)
    v1fdat = np.array(v1fdat)
    u2fdat = np.array(u2fdat)
    v2fdat = np.array(v2fdat)
    t3wavedat = np.array(t3wavedat)
    t3phidat = np.array(t3phidat)
    t3phierr = np.array(t3phierr)

    u3fdat = u1fdat + u2fdat  # 3d baseline (frequency) and max baseline of closure triangle (in MegaLambda)
    v3fdat = v1fdat + v2fdat
    bmax = np.maximum(np.sqrt(u3fdat ** 2 + v3fdat ** 2),
                      np.maximum(np.sqrt(u1fdat ** 2 + v1fdat ** 2),
                                 np.sqrt(u2fdat ** 2 + v2fdat ** 2))) / 1e6

    obsvbs_dat['uf'] = ufdat  # fill in data observables dictionary
    obsvbs_dat['vf'] = vfdat
    obsvbs_dat['wave'] = wavedat
    obsvbs_dat['v2'] = v2dat
    obsvbs_dat['v2err'] = v2err
    obsvbs_dat['base'] = base

    obsvbs_dat['u1f'] = u1fdat
    obsvbs_dat['v1f'] = v1fdat
    obsvbs_dat['u2f'] = u2fdat
    obsvbs_dat['v2f'] = v2fdat
    obsvbs_dat['u3f'] = u3fdat
    obsvbs_dat['v3f'] = v3fdat
    obsvbs_dat['bmax'] = bmax
    obsvbs_dat['t3wave'] = t3wavedat
    obsvbs_dat['t3phi'] = t3phidat
    obsvbs_dat['t3phierr'] = t3phierr

    return obsvbs_dat


def calc_model_observables(data_dir, data_file, mod_dir, img_dir=None, monochr=False, disk_only=False,
                           wavelim_lower=None, wavelim_upper=None, plotting=False, fig_dir=None):
    """
    Function that loads in the OIFITS observations and calculates MCFOST model observables at the same spatial
    frequencies. The monochromatism 'monochr' argument can be used to use only observation data between a
    wavelength interval (wavelim_lower, wavelim_upper). In this case the 'img_dir' argument needs to be specified, as
    only the specific MCFOST .fits.gz output image file in img_dir will be used for calculating the FFT.
    No interpolation in the wavelength dimension will be performed. If monochr=True, all image subdirectories in
    the directory 'mod_dir'+'img_dir' will instead be used to interpolate between wavelengths. In this case
    the wavelength coverage of the MCFOST images needs to be wider than that of the data, otherwise an error is
    thrown. Spatial frequencies, wavelengths and observables are returned in dictionaries.
    """

    # retrieve dictionary observation observables
    obsvbs_dat = get_observation_data(data_dir, data_file, wavelim_lower=wavelim_lower,
                                      wavelim_upper=wavelim_upper)

    # Return model observables in a nice dictionary format
    obsvbs_mod = {}

    if monochr:
        # perform FFT on single image and return appropriate interpolators
        interp_v2, interp_phi = perform_fft(mod_dir, img_dir, plotting=False, addinfo=False,
                                            disk_only=disk_only, fig_dir=fig_dir)
        # model observables calculation
        v2mod = interp_v2((obsvbs_dat['uf'], obsvbs_dat['vf']))  # interpolate model V2 at data uv coverage
        phi1mod = interp_phi((obsvbs_dat['u1f'], obsvbs_dat['v1f']))  # interpolate model complex phases
        phi2mod = interp_phi((obsvbs_dat['u2f'], obsvbs_dat['v2f']))
        phi3mod = interp_phi((obsvbs_dat['u3f'], obsvbs_dat['v3f']))
        # We use the convention such that triangle ABC -> (u1,v1) = AB; (u2,v2) = BC; (u3,v3) = AC, not CA
        # This causes a minus sign shift for 3rd baseline when calculating closure phase (for real images)
        t3phimod = phi1mod + phi2mod - phi3mod

        obsvbs_mod['v2'] = v2mod  # fill in the model observables dictionary
        obsvbs_mod['phi1'] = phi1mod
        obsvbs_mod['phi2'] = phi2mod
        obsvbs_mod['phi3'] = phi3mod
        obsvbs_mod['t3phi'] = t3phimod

        if plotting:
            # plot uv coverage
            fig, ax = plt.subplots(1, 1, figsize=(5, 5))

            ax.scatter(obsvbs_dat['uf'] / 1e6, obsvbs_dat['vf'] / 1e6, s=2, color='b')
            ax.scatter(-obsvbs_dat['uf'] / 1e6, -obsvbs_dat['vf'] / 1e6, s=2, color='b')

            ax.set_xlim(ax.get_xlim()[::-1])
            ax.set_title('uv coverage')
            ax.set_xlabel(r"$\leftarrow B_u$ ($\mathrm{M \lambda}$)")
            ax.set_ylabel(r"$B_v \rightarrow$ ($\mathrm{M \lambda}$)")
            plt.tight_layout()
            plt.savefig(f"{fig_dir}/cwave_uv_plane.png", dpi=300)

            # plot V2
            fig = plt.figure(figsize=(6, 6))
            gs = fig.add_gridspec(2, hspace=0, height_ratios=[1, 0.3])
            ax = gs.subplots(sharex=True)

            ax[0].errorbar(obsvbs_dat['base'], obsvbs_dat['v2'], obsvbs_dat['v2err'], label='data', fmt='bd',
                           mfc='white', capsize=0, zorder=1000, markersize=4, elinewidth=0.5)
            ax[0].scatter(obsvbs_dat['base'], obsvbs_mod['v2'], label='MCFOST model', marker='o',
                          color='r', s=4)
            ax[1].scatter(obsvbs_dat['base'], (obsvbs_mod['v2'] - obsvbs_dat['v2']) / obsvbs_dat['v2err'],
                          marker='o', color='r', s=4)

            ax[0].set_ylabel('$V^2$')
            ax[0].set_ylim(0, 1)
            ax[0].legend()
            ax[0].set_title('Squared Visibilities')
            ax[0].tick_params(axis="x", direction="in", pad=-15)

            ax[1].set_xlim(0, np.max(obsvbs_dat['base']) * 1.05)
            ax[1].axhline(y=0, c='k', ls='--', lw=1, zorder=0)
            ax[1].set_xlabel(r'$B$ ($\mathrm{M \lambda}$)')
            ax[1].set_ylabel(r'error $(\sigma_{V^2})$')

            plt.savefig(f"{fig_dir}/cwave_V2.png", dpi=300)

            # plot phi_closure
            fig = plt.figure(figsize=(6, 6))
            gs = fig.add_gridspec(2, hspace=0, height_ratios=[1, 0.3])
            ax = gs.subplots(sharex=True)

            ax[0].errorbar(obsvbs_dat['bmax'], obsvbs_dat['t3phi'], obsvbs_dat['t3phierr'], label='data',
                           fmt='bd', mfc='white', capsize=0, zorder=1000, markersize=4, elinewidth=0.5)
            ax[0].scatter(obsvbs_dat['bmax'], obsvbs_mod['t3phi'], label='MCFOST model', marker='o',
                          color='r', s=4)
            ax[1].scatter(obsvbs_dat['bmax'], (obsvbs_mod['t3phi'] - obsvbs_dat['t3phi']) / obsvbs_dat['t3phierr'],
                          marker='o', color='r', s=4)

            ax[0].set_ylabel(r'$\phi_{CP}$ ($^\circ$)')
            ax[0].legend()
            ax[0].set_title('Closure Phases')
            ax[0].tick_params(axis="x", direction="in", pad=-15)

            ax[1].set_xlim(0, np.max(obsvbs_dat['bmax']) * 1.05)
            ax[1].axhline(y=0, c='k', ls='--', lw=1, zorder=0)
            ax[1].set_xlabel(r'$B_{max}$ ($\mathrm{M \lambda}$)')
            ax[1].set_ylabel(r'error $(\sigma_{\phi_{CP}})$')

            plt.savefig(f"{fig_dir}/cwave_t3phi.png", dpi=300)

    elif not monochr:
        #         # Load in all data without wavelength limits
        #         oidata = oifits.data(data_dir, data_file)
        #         print('suprise')
        #         for vis2table in oidata.vis2:
        #             print(vis2table.uf)
        print('suprise')

    return obsvbs_dat, obsvbs_mod


if __name__ == '__main__':
    data_dir = '/home/toond/Documents/phd/MCFOST/recr_corporaal_et_al2023/data/PIONIER/'
    data_file = 'IRAS08544-4431_PIONIER_data2015ep.fits'
    mod_dir = '/home/toond/Documents/phd/MCFOST/recr_corporaal_et_al2023/models_akke_mcfost/best_model1_largeFOV'
    img_dir = 'PIONIER/data_1.6'
    fig_dir = '/home/toond/Downloads/figs'

    interp_v2, interp_phi = perform_fft(mod_dir, img_dir, plotting=True, addinfo=True,
                                        disk_only=False, fig_dir=fig_dir)

    obsvbs_dat, obsvbs_mod = calc_model_observables(data_dir, data_file, mod_dir,
                                                    monochr=True, img_dir=img_dir, wavelim_lower=1.63,
                                                    wavelim_upper=1.67, plotting=True, fig_dir=fig_dir)
