### Essential reprducibility checklist for authors in the Biometrical Journal

We ask you to carefully read through our Reproducible Research (RR) checklist to make sure that your submission follows best practices
for reproducible scientific computing. Please check the following items to certify that you have addressed them in
your code submission. Note that your reproducibility editor will ask for an explanation of any missing checkmark. The sooner you can adhere to this checklist, the faster your audit will be.

- [ ] Include a README file: either README.txt , README.md or README.pdf , following the specifications in the RR guideline linked above. Please do not forget to add version and dependencies information at its end, by, e.g., copy-pasting the output of R’s sessionInfo() AFTER loading all necessary packages.

- [ ] Describe how to run your code: your README file must describe exactly how to run your code, i.e. which
files need to be run in wich order. Or even better, also create only one main file (e.g., main.R or
main.py ) that proceeds through running the different scripts in an ordely fashion to go through your
manuscript by executing one single command, recreating all results, i.e., tables, figures and numbers.

- [ ] Include all code and data necessary to reproduce all figures, tables and results in your paper: if
data are not allowed to be made public, pseudo data that are comparable to the original data in size and
structure can be used instead. If at all possible, the original data should be made available privately at
least to RR editors for the strict purpose of the audit.

- [ ] Ensure that the results from your code are clearly linked to the results in the paper: e.g. by exporting
the figures and tables to appropriately named files (e.g. table1.csv, figure1.pdf).

- [ ] Report the runtime of your code, and what hardware you used: in your README file. Order of magni-
tude should suffice (make clear if the code needs a couple minutes, a few hours, or many days to complete).

- [ ] Explain the use of parallelisation: if your code runs in parallel, please state so in the README file and
describe how it can be adapted to the users’ own set-up.

- [ ] Avoid absolute paths: only use paths relative to either the current file, or the working directory if the latter
is specified in the README and script file (e.g., ./script.R , or data/ ). If this is impossible, clearly
state in your README why and how to change the paths. Refrain from setting or changing the working
directory in your code.

- [ ] Organise your code well: use sensible folder structures, sensible file names, sensible variable names, and
avoid code duplication thanks to the use of functions.

- [ ] Add helpful comments: in particular add comments that state what figure or table in the manuscript the
code produces and make it as easy as possible to associate the outputs of your code with the results in the
manuscript.

- [ ] Ensure simulations are reproducible: all code that relies on results of a random number generator must
absolutely be initiated by seeds, so that results are reproducible.

- [ ] Provide intermediate results or reduce simulation number: if the computations run for more than a
couple of hours on a standard laptop, please send along intermediate results. This will enable us to perform
spot checks of reproducibility without having to re-run your entire simulation study. If files containing
intermediate results are too large to share via e-mail, please upload them to a data repository such as, e.g.,
zenodo, figshare or osf.io. Alternatively, provide results for a reduced number of repetitions that allows to
extrapolate reproducibility for the fully sized simulations.

- [ ] All code files, data and the README should be contained in one single ZIP container: e.g.
Code_and_Data.zip , possibly with subfolders in the container to organize the codebase. Strip that
.zip container of any unnecessary files.