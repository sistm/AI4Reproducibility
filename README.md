# AI4reproducibility
Authors : Jad El Karchi; <jad.el-karchi@u-bordeaux.fr> 

![Python](https://img.shields.io/badge/Python-3.12+-blue)
![Docker](https://img.shields.io/badge/Docker-29.2.1+-blue)

> AI4Reproducibility is a framework for building agentic AI systems that automatically evaluate the reproducibility of scientific papers.



## Problem 

Scientific reproducibility is one of the most important pillars of research integrity. However, verifying reproducibility during the peer-review process is often:

- Time-consuming
- Subjective
- Inconsistent across reviewers
- Difficult to standardize


## Goal 
The project aims mainly to create a pipeline of automated AI agents designed to evaluate the reproducibility of scientific paper submissions. This pipeline provides a detailed assessment of each major criterion involved in determining the research quality and reproducibility standards required for the acceptance of a submitted paper.

## Requirements

To run this project, ensure the following dependencies are installed:

- **Python ≥ 3.12**
- **Docker ≥ 29.2.1**

Docker is required to create isolated and reproducible execution environments for running experiment validation pipelines.

## Repository Structure
```bash
ai4reproducibility/
│
├── CHECKLIST.md # Reproducibility evaluation criteria.
│
├── LOGIC.md # Description of the agentic evaluation pipeline.
│
├── agents/ # Specialized agents for different analysis tasks.
│
├── tools/ # External tools used by the agents (code execution, dataset checks, etc.)
│
└── papers/ # Sample paper evaluations and reports.
│
└── app/ # simple web application implementing the pipeline with a user friendly interface
│
└── assets/ # images/media content   
```

# Method 

The system uses a multi-agent architecture where each agent specializes in evaluating specific aspects of the paper.

- **Knowledge Extraction Agent** : Understand the context, and extract domain expertise from different assets of the submission, **excluding experiments & code**. Gives a detailed and global understanding on where the paper really stands in research. 

- **Preliminary Code Verification Agent** : Code has an online repository exists, a clear README description, Code matches the described method, Dependencies are documented, Data accessibility, Licensing, versionning...

- **Experimental Agent** : Evaluates whether the experiments described in the paper can be reproduced based on the information provided. To support this process, the agent can create a fully isolated code execution environment using **Docker**, enabling safe and controlled validation of the experimental setup.

- **Review Agent** : Uses the outputs produced by the previous agents together with the criteria defined in the `CHECKLIST.md`. Through iterative reasoning and self-critique, the agent evaluates the gathered evidence and generates a comprehensive reproducibility assessment.

This work is done using methods such as prompt alignment, tool creation, and system design to give access to paper reviewers to a reliable and deterministic valuation of the submitted paper. 

**N.B.**: The pipeline is designed to be **fail-safe**. Even if a paper is flagged or rejected by one agent, it is still passed to the subsequent agents for further analysis. This guarantees that a complete JSON analysis report is generated at the end of the pipeline.

## AI : general rule 

Prompts must be carefully designed to ensure deterministic and reliable outputs from the language model. Since language models are inherently probabilistic models, they can sometimes produce hallucinations or misinformation. Therefore, this tool should be used with moderation and human supervision to ensure consistent, coherent, and trustworthy results across paper evaluations.

Finally, AI ouputs are required to follow structured output formats (e.g., JSON), enabling automated parsing, transparent evaluation metrics, and seamless integration into web applications.
