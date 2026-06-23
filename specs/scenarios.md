# specs/scenarios.md
#
# Role: BDD Gherkin scenarios for the Voice-Aware Content Engine.
#       These define the expected behaviour for both the happy path and
#       edge cases across all pipeline agents.
#
# Governed by: specs/SPEC.md Section 13.
# Run via:     agents-cli eval (or a BDD runner like pytest-bdd)
#
# Keep these in sync with the eval cases in specs/evals/.

Feature: Voice-aware content generation

  Scenario: Produce an on-brand article from a chosen trend
    Given a saved voice_profile and topic_seeds
    When the user triggers a run and selects a topic from the candidates
    Then serp_findings, angle_brief, draft and final_article are produced in order
    And final_article reflects the voice_profile tone and includes every must_include item

  Scenario: No fresh trend is available
    Given topic_seeds exist but search returns nothing timely
    When trend_scout runs
    Then it proposes evergreen angles from topic_seeds
    And it flags them as evergreen rather than trending

  Scenario: A source is blocked by terms of use
    Given the fetch tool returns content from a non-allowlisted domain
    When the policy callback runs
    Then the content is dropped
    And policy_notes records the skipped source
    And the pipeline continues without it

  Scenario: PII appears in the draft
    Given a draft containing an email address
    When editor_guard runs
    Then the email is removed from final_article
    And policy_notes records that PII was stripped

  Scenario: Voice clip is too short
    Given an uploaded clip shorter than 20 seconds
    When voice_profile_builder runs
    Then it asks the user to re-record
    And it does not fabricate a voice_profile
