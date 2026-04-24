######################
Verifying CDF contents
######################

The following page describes methods for verifying CDF files after they are created by IMAP processing software.


*********
SKTeditor
*********

After CDF files are generated, it is helpful to check for any compliance errors using the `SKTeditor <https://spdf.gsfc.nasa.gov/skteditor/>`_ tool.

You can download this tool from the link above, and open the created file there.  You can click "Show Messages" in the lower right-hand corner, and it will provide details about any ISTP compliance errors that the code may have missed.


***************************
Command-line SPDF checking
***************************

IMAP processing also supports the official SPDF command-line checker built into
SKTEditor. The validator entry point documented by SPDF is:

.. code-block:: bash

   java -cp spdfjavaClasses.jar:$CDF_LIB/cdfjava.jar \
     gsfc.spdf.istp.tools.CDFCheck filename.cdf

For local Linux setup in this repository, use the helper installer:

.. code-block:: bash

   bash tools/spdf/install_spdf_validator_linux.sh .spdf-tools > .spdf-tools/env.sh
   source .spdf-tools/env.sh

Then validate one or more generated CDFs with:

.. code-block:: bash

   poetry run python -m imap_processing.cdf.spdf_validation path/to/file.cdf

The installer script downloads the official NASA CDF distribution from
``cdf.gsfc.nasa.gov`` and the official SKTEditor package from
``spdf.gsfc.nasa.gov``. In CI we use the same flow on Ubuntu so that the SPDF
validation step is separate from the main pytest matrix.


***************
SPDF Validation
***************

As a final validation step, the SPDF will review all completed data products.  They will run the CDF file through the SKTeditor as a first pass, and also ensure that the auto-generated plots look nice on CDAWeb using the IDL tool `https://cdaweb.gsfc.nasa.gov/cdfx/ <https://cdaweb.gsfc.nasa.gov/cdfx/>`_.

They will also perform a final check on all of the attribute values to ensure they make sense from a user perspective. Some examples of errors caught so far include:

* The ``TEXT`` global attribute needs to be longer
* ``VALIDMIN`` and ``VALIDMAX`` need to be reasonable numbers
* ``FIELDNAM`` and ``CATDESC`` need to be more descriptive
* ``Logical_source_description`` needs to be more formal, like ``Low gain channel of the time-of-flight signal`` instead of ``This is the variable for....``
* "Metadata" fields from the CCSDS packet should be made into ``VAR_YPE=data`` rather than ``support_data`` or ``metadata``
   * ``support_data`` is reserved for coordinate data, i.e. the variable that other ``DEPEND_{i}`` attributes point to
   * metadata is reserved for text-based variable, like pointers to text labels
