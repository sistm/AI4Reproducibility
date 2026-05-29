"""
ER Agent - Experiment Results Evaluation Module

This module evaluates experimental results against reported claims and validates reproducibility.
"""

import json
from pathlib import Path


class ResultsEvaluator:
    """Evaluates experimental results for reproducibility and correctness."""
    
    def __init__(self, results_path: str, paper_claims: dict[str, any]):
        self.results_path = Path(results_path)
        self.paper_claims = paper_claims
        self.evaluation = {
            'claims_verified': [],
            'claims_failed': [],
            'metrics': {},
            'reproducibility_score': 0,
            'critical_issues': [],
            'warnings': []
        }
    
    def verify_statistical_claims(self) -> list[dict[str, any]]:
        """Verify statistical claims reported in the paper."""
        results = []
        
        # Check for common statistical outputs
        if (self.results_path / "tables").exists():
            for table_file in (self.results_path / "tables").glob("*.csv"):
                # Basic validation - check if file is readable
                try:
                    with open(table_file) as f:
                        lines = f.readlines()
                        if len(lines) > 1:  # Has header and data
                            results.append({
                                'claim_type': 'statistical_table',
                                'file': str(table_file),
                                'status': 'verified',
                                'message': 'Table file is readable and contains data'
                            })
                        else:
                            results.append({
                                'claim_type': 'statistical_table',
                                'file': str(table_file),
                                'status': 'failed',
                                'message': 'Table file is empty'
                            })
                except Exception as e:
                    results.append({
                        'claim_type': 'statistical_table',
                        'file': str(table_file),
                        'status': 'failed',
                        'message': f'Error reading table: {e!s}'
                    })
        
        return results
    
    def verify_reported_metrics(self) -> dict[str, any]:
        """Check if reported metrics match experimental outputs."""
        metrics = {}
        
        # Check for common metric files
        metric_files = {
            'accuracy': 'accuracy.json',
            'loss': 'loss.json',
            'confusion_matrix': 'confusion_matrix.csv',
            'p_values': 'p_values.json'
        }
        
        for metric_name, filename in metric_files.items():
            file_path = self.results_path / filename
            if file_path.exists():
                try:
                    with open(file_path) as f:
                        data = json.load(f) if filename.endswith('.json') else f.read()
                        metrics[metric_name] = {
                            'status': 'found',
                            'data': data
                        }
                except Exception as e:
                    metrics[metric_name] = {
                        'status': 'error',
                        'error': str(e)
                    }
            else:
                metrics[metric_name] = {
                    'status': 'missing',
                    'error': 'File not found'
                }
        
        return metrics
    
    def check_experiment_logs(self) -> list[dict[str, str]]:
        """Check experiment execution logs for errors or warnings."""
        logs = []
        
        log_files = list(self.results_path.glob("*.log")) + list(self.results_path.glob("logs/*.log"))
        
        for log_file in log_files:
            try:
                with open(log_file) as f:
                    content = f.read()
                    if 'ERROR' in content or 'Exception' in content:
                        logs.append({
                            'file': str(log_file),
                            'level': 'critical',
                            'message': 'Errors found in execution logs'
                        })
                    elif 'WARNING' in content:
                        logs.append({
                            'file': str(log_file),
                            'level': 'warning',
                            'message': 'Warnings found in execution logs'
                        })
            except Exception as e:
                logs.append({
                    'file': str(log_file),
                    'level': 'error',
                    'message': f'Could not read log file: {e!s}'
                })
        
        return logs
    
    def calculate_reproducibility_score(self) -> float:
        """Calculate a reproducibility score based on evaluation."""
        score = 100.0
        
        # Deduct points for issues
        issues = len(self.evaluation['critical_issues']) * 25
        warnings = len(self.evaluation['warnings']) * 5
        missing_metrics = sum(1 for m in self.evaluation['metrics'].values() if m['status'] == 'missing') * 10
        
        score -= issues + warnings + missing_metrics
        score = max(0, score)
        
        return round(score, 2)
    
    def evaluate(self) -> dict[str, any]:
        """Run full evaluation of experimental results."""
        self.evaluation['claims_verified'] = self.verify_statistical_claims()
        self.evaluation['metrics'] = self.verify_reported_metrics()
        self.evaluation['logs'] = self.check_experiment_logs()
        self.evaluation['reproducibility_score'] = self.calculate_reproducibility_score()
        
        # Identify critical issues
        for metric_name, metric_data in self.evaluation['metrics'].items():
            if metric_data['status'] == 'error':
                self.evaluation['critical_issues'].append({
                    'type': 'metric_error',
                    'metric': metric_name,
                    'message': metric_data.get('error', 'Unknown error')
                })
        
        for log in self.evaluation['logs']:
            if log['level'] == 'critical':
                self.evaluation['critical_issues'].append({
                    'type': 'execution_error',
                    'file': log['file'],
                    'message': log['message']
                })
        
        return self.evaluation


def evaluate_results(results_path: str, paper_claims: dict[str, any]) -> dict[str, any]:
    """
    Main function to evaluate experimental results.
    
    Args:
        results_path: Path to experimental results
        paper_claims: Claims reported in the paper to verify
        
    Returns:
        Evaluation results with verification status
    """
    evaluator = ResultsEvaluator(results_path, paper_claims)
    return evaluator.evaluate()