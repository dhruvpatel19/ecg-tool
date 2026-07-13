# PTB-derived clean-runner test corpus

`ptb_ci_corpus.tar.gz` contains a minimized subset of 103 real ECG waveforms
from PTB-XL, plus the PTB-XL+ derived evidence needed to validate the authored
Clinical bank on a clean CI runner. It is source-test data only; production uses
the complete independently audited release corpus.

The export removes stable patient identifiers, recording dates, source file
paths, staff/site/device fields, and validator identifiers. It preserves only
the ECG signal and educational evidence required by the tests.

- PTB-XL 1.0.3: Wagner et al., “PTB-XL, a large publicly available
  electrocardiography dataset,” DOI <https://doi.org/10.1038/s41597-020-0495-6>,
  source <https://physionet.org/content/ptb-xl/1.0.3/>.
- PTB-XL+ 1.0.1: Strodthoff et al., DOI
  <https://doi.org/10.13026/g6h6-7g88>, source
  <https://physionet.org/content/ptb-xl-plus/1.0.1/>.
- License: Creative Commons Attribution 4.0 International,
  <https://creativecommons.org/licenses/by/4.0/>.

No clinical-management or acute-event ground truth is inferred from this test
asset. The authored vignettes remain simulations grounded to real ECG evidence.
