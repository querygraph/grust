"""Separate a completed partial WCC check from independently verified results."""
import argparse


PARTIALLY_VERIFIED = 'partially_verified'


def effective_outcome(receipt, *, outcome=None):
    """Derive scope without changing an original receipt or masking a failure."""
    reported = receipt.get('outcome', 'invalid_receipt') if outcome is None else outcome
    correctness = receipt.get('correctness') or {}
    arguments = receipt.get('arguments') or {}
    if (reported == 'passed' and arguments.get('algorithm') == 'wcc' and
            correctness.get('policy') == 'certificate' and
            correctness.get('component_count_verified') is False):
        return PARTIALLY_VERIFIED
    return reported


def expected_validation_outcome(command):
    """Read the effective flags, including any final extra-cell overrides."""
    parser = argparse.ArgumentParser(add_help=False, allow_abbrev=False)
    parser.add_argument('--algorithm')
    parser.add_argument('--ranking-validation', default='reference')
    arguments, _ = parser.parse_known_args(command)
    return (PARTIALLY_VERIFIED if arguments.algorithm == 'wcc' and
            arguments.ranking_validation == 'certificate' else 'passed')


def resumed_outcome(result, receipt, expected):
    """Restate a legacy summary in memory; retain its original outcome labels."""
    if result.get('outcome') != 'passed' or effective_outcome(receipt) != PARTIALLY_VERIFIED:
        return result
    return dict(result, original_outcome=result['outcome'],
                original_expected_outcome=result.get('expected_outcome'),
                outcome=PARTIALLY_VERIFIED, expected_outcome=expected,
                expected_outcome_observed=expected == PARTIALLY_VERIFIED)
