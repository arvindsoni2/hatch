-- Canonical current-metadata schema fixture for Coach PR1 migration tests.

-- Source integration SHA: 52ded582babf684e90325f000233e811914f7710

-- Alembic revision: p3q4r5s6t7u8

-- Order: sqlite_schema.type ASC, sqlite_schema.name ASC; SQLite internals excluded.

-- index: idx_activity_log_app_id
CREATE INDEX idx_activity_log_app_id ON activity_log (application_id);

-- index: idx_application_outcomes_application_id
CREATE INDEX idx_application_outcomes_application_id ON application_outcomes (application_id);

-- index: idx_application_outcomes_occurred_at
CREATE INDEX idx_application_outcomes_occurred_at ON application_outcomes (occurred_at);

-- index: idx_application_outcomes_type
CREATE INDEX idx_application_outcomes_type ON application_outcomes (outcome_type);

-- index: idx_application_score_snapshots_created_at
CREATE INDEX idx_application_score_snapshots_created_at ON application_score_snapshots (created_at);

-- index: idx_application_score_snapshots_job_id
CREATE INDEX idx_application_score_snapshots_job_id ON application_score_snapshots (job_id);

-- index: idx_application_score_snapshots_role_family
CREATE INDEX idx_application_score_snapshots_role_family ON application_score_snapshots (role_family);

-- index: idx_application_score_snapshots_source
CREATE INDEX idx_application_score_snapshots_source ON application_score_snapshots (source);

-- index: idx_applications_job_id
CREATE INDEX idx_applications_job_id ON applications (job_id);

-- index: idx_applications_status
CREATE INDEX idx_applications_status ON applications (status);

-- index: idx_applications_updated_at
CREATE INDEX idx_applications_updated_at ON applications (updated_at);

-- index: idx_async_jobs_created_at
CREATE INDEX idx_async_jobs_created_at ON async_jobs (created_at);

-- index: idx_async_jobs_status_type
CREATE INDEX idx_async_jobs_status_type ON async_jobs (status, type);

-- index: idx_company_research_expires
CREATE INDEX idx_company_research_expires ON company_research (expires_at);

-- index: idx_company_research_name
CREATE INDEX idx_company_research_name ON company_research (company_name);

-- index: idx_company_watchlist_last_scanned
CREATE INDEX idx_company_watchlist_last_scanned ON company_watchlist_items (last_scanned_at);

-- index: idx_company_watchlist_status_frequency
CREATE INDEX idx_company_watchlist_status_frequency ON company_watchlist_items (status, scan_frequency);

-- index: idx_cost_agent_date
CREATE INDEX idx_cost_agent_date ON cost_tracking (agent_name, created_at);

-- index: idx_cost_job_id
CREATE INDEX idx_cost_job_id ON cost_tracking (job_id);

-- index: idx_events_created
CREATE INDEX idx_events_created ON agent_events (created_at);

-- index: idx_events_status
CREATE INDEX idx_events_status ON agent_events (status, event_type);

-- index: idx_follow_up_emails_application_id
CREATE INDEX idx_follow_up_emails_application_id ON follow_up_emails (application_id);

-- index: idx_follow_up_emails_created_at
CREATE INDEX idx_follow_up_emails_created_at ON follow_up_emails (created_at);

-- index: idx_follow_up_emails_status
CREATE INDEX idx_follow_up_emails_status ON follow_up_emails (status);

-- index: idx_follow_ups_app_id
CREATE INDEX idx_follow_ups_app_id ON follow_ups (application_id);

-- index: idx_follow_ups_completed
CREATE INDEX idx_follow_ups_completed ON follow_ups (completed);

-- index: idx_follow_ups_due_date
CREATE INDEX idx_follow_ups_due_date ON follow_ups (due_date);

-- index: idx_generated_docs_application_id
CREATE INDEX idx_generated_docs_application_id ON generated_documents (application_id);

-- index: idx_generated_docs_status
CREATE INDEX idx_generated_docs_status ON generated_documents (status);

-- index: idx_generated_document_assets_application_id
CREATE INDEX idx_generated_document_assets_application_id ON generated_document_assets (application_id);

-- index: idx_generated_document_assets_source_document_id
CREATE INDEX idx_generated_document_assets_source_document_id ON generated_document_assets (source_document_id);

-- index: idx_generated_document_assets_status
CREATE INDEX idx_generated_document_assets_status ON generated_document_assets (generation_status);

-- index: idx_interview_rounds_app_id
CREATE INDEX idx_interview_rounds_app_id ON interview_rounds (application_id);

-- index: idx_interview_rounds_scheduled_at
CREATE INDEX idx_interview_rounds_scheduled_at ON interview_rounds (scheduled_at);

-- index: idx_interview_sessions_application_id
CREATE INDEX idx_interview_sessions_application_id ON interview_sessions (application_id);

-- index: idx_interview_sessions_created_at
CREATE INDEX idx_interview_sessions_created_at ON interview_sessions (created_at);

-- index: idx_interview_sessions_status
CREATE INDEX idx_interview_sessions_status ON interview_sessions (status);

-- index: idx_job_postings_active_scraped
CREATE INDEX idx_job_postings_active_scraped ON job_postings (is_active, scraped_at);

-- index: idx_job_postings_ghost_score
CREATE INDEX idx_job_postings_ghost_score ON job_postings (ghost_score);

-- index: idx_job_postings_ghost_verdict
CREATE INDEX idx_job_postings_ghost_verdict ON job_postings (ghost_verdict);

-- index: idx_opportunity_scores_calculated_at
CREATE INDEX idx_opportunity_scores_calculated_at ON opportunity_scores (calculated_at);

-- index: idx_opportunity_scores_score
CREATE INDEX idx_opportunity_scores_score ON opportunity_scores (opportunity_score);

-- index: idx_question_bank_archived_at
CREATE INDEX idx_question_bank_archived_at ON question_bank_items (archived_at);

-- index: idx_question_bank_confidence
CREATE INDEX idx_question_bank_confidence ON question_bank_items (confidence);

-- index: idx_question_bank_type
CREATE INDEX idx_question_bank_type ON question_bank_items (type);

-- index: idx_question_bank_updated_at
CREATE INDEX idx_question_bank_updated_at ON question_bank_items (updated_at);

-- index: idx_role_fingerprint_external
CREATE INDEX idx_role_fingerprint_external ON discovered_role_fingerprints (normalized_company, external_job_id);

-- index: idx_role_fingerprint_source_url
CREATE INDEX idx_role_fingerprint_source_url ON discovered_role_fingerprints (source_url);

-- index: idx_role_fingerprint_title_location
CREATE INDEX idx_role_fingerprint_title_location ON discovered_role_fingerprints (normalized_company, normalized_title, normalized_location);

-- index: idx_scores_overall
CREATE INDEX idx_scores_overall ON job_scores (overall_score);

-- index: idx_session_questions_session_id
CREATE INDEX idx_session_questions_session_id ON session_questions (session_id);

-- index: idx_session_recordings_question_id
CREATE INDEX idx_session_recordings_question_id ON session_recordings (question_id);

-- index: idx_session_recordings_session_id
CREATE INDEX idx_session_recordings_session_id ON session_recordings (session_id);

-- index: idx_stories_created_at
CREATE INDEX idx_stories_created_at ON stories (created_at);

-- index: idx_stories_is_active
CREATE INDEX idx_stories_is_active ON stories (is_active);

-- index: idx_stories_strength_score
CREATE INDEX idx_stories_strength_score ON stories (strength_score);

-- index: idx_story_usages_session_id
CREATE INDEX idx_story_usages_session_id ON story_usages (session_id);

-- index: idx_story_usages_story_id
CREATE INDEX idx_story_usages_story_id ON story_usages (story_id);

-- index: idx_tailoring_reviews_application_created
CREATE INDEX idx_tailoring_reviews_application_created ON tailoring_reviews (application_id, created_at);

-- index: ix_app_lock_sessions_expires_at
CREATE INDEX ix_app_lock_sessions_expires_at ON app_lock_sessions (expires_at);

-- index: ix_app_lock_sessions_session_hash
CREATE UNIQUE INDEX ix_app_lock_sessions_session_hash ON app_lock_sessions (session_hash);

-- table: activity_log
CREATE TABLE activity_log (
	id INTEGER NOT NULL,
	application_id VARCHAR(36) NOT NULL,
	action VARCHAR(64) NOT NULL,
	old_value VARCHAR(512),
	new_value VARCHAR(512),
	detail TEXT,
	created_at DATETIME NOT NULL,
	PRIMARY KEY (id),
	FOREIGN KEY(application_id) REFERENCES applications (id)
);

-- table: agency_reputations
CREATE TABLE agency_reputations (
	id VARCHAR(36) NOT NULL,
	agency_name VARCHAR(256) NOT NULL,
	total_jobs_posted INTEGER NOT NULL,
	total_applications INTEGER NOT NULL,
	total_responses INTEGER NOT NULL,
	response_rate FLOAT NOT NULL,
	avg_ghost_score FLOAT NOT NULL,
	reputation VARCHAR(16) NOT NULL,
	last_updated DATETIME NOT NULL,
	PRIMARY KEY (id),
	UNIQUE (agency_name)
);

-- table: agent_events
CREATE TABLE agent_events (
	id VARCHAR(36) NOT NULL,
	event_type VARCHAR(64) NOT NULL,
	source_agent VARCHAR(32) NOT NULL,
	payload TEXT NOT NULL,
	status VARCHAR(16) NOT NULL,
	created_at DATETIME NOT NULL,
	processed_at DATETIME,
	error_message TEXT,
	PRIMARY KEY (id)
);

-- table: agent_state
CREATE TABLE agent_state (
	agent_name VARCHAR(32) NOT NULL,
	last_run_at DATETIME,
	status VARCHAR(32) NOT NULL,
	current_task TEXT,
	config TEXT,
	updated_at DATETIME NOT NULL,
	PRIMARY KEY (agent_name)
);

-- table: alembic_version
CREATE TABLE alembic_version (
	version_num VARCHAR(32) NOT NULL,
	CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num)
);

-- table: app_lock_config
CREATE TABLE app_lock_config (
	id INTEGER NOT NULL,
	password_hash VARCHAR(255),
	last_unlocked_at DATETIME,
	last_password_changed_at DATETIME,
	failed_attempt_count INTEGER NOT NULL,
	last_failed_attempt_at DATETIME,
	created_at DATETIME NOT NULL,
	updated_at DATETIME NOT NULL,
	PRIMARY KEY (id)
);

-- table: app_lock_sessions
CREATE TABLE app_lock_sessions (
	id VARCHAR(36) NOT NULL,
	session_hash VARCHAR(64) NOT NULL,
	created_at DATETIME NOT NULL,
	last_seen_at DATETIME NOT NULL,
	expires_at DATETIME NOT NULL,
	PRIMARY KEY (id)
);

-- table: application_outcomes
CREATE TABLE application_outcomes (
	id VARCHAR(36) NOT NULL,
	application_id VARCHAR(36) NOT NULL,
	outcome_type VARCHAR(32) NOT NULL,
	occurred_at DATETIME NOT NULL,
	source VARCHAR(32) NOT NULL,
	metadata_json JSON,
	created_at DATETIME NOT NULL,
	PRIMARY KEY (id),
	CONSTRAINT uq_application_outcomes_app_type UNIQUE (application_id, outcome_type),
	FOREIGN KEY(application_id) REFERENCES applications (id)
);

-- table: application_score_snapshots
CREATE TABLE application_score_snapshots (
	id VARCHAR(36) NOT NULL,
	application_id VARCHAR(36) NOT NULL,
	job_id VARCHAR(36),
	base_fit_score FLOAT,
	skill_match FLOAT,
	experience_match FLOAT,
	rate_match FLOAT,
	location_match FLOAT,
	source VARCHAR(64),
	role_family VARCHAR(256),
	seniority VARCHAR(32),
	working_pattern VARCHAR(32),
	employment_type VARCHAR(32),
	ir35_status VARCHAR(32),
	freshness_bucket VARCHAR(32),
	job_age_days INTEGER,
	cv_variant VARCHAR(8),
	cl_variant VARCHAR(8),
	scoring_method VARCHAR(20),
	scorer_version VARCHAR(32) NOT NULL,
	snapshot_quality VARCHAR(16) NOT NULL,
	created_at DATETIME NOT NULL,
	PRIMARY KEY (id),
	CONSTRAINT uq_application_score_snapshots_application_id UNIQUE (application_id),
	FOREIGN KEY(application_id) REFERENCES applications (id),
	FOREIGN KEY(job_id) REFERENCES job_postings (id)
);

-- table: applications
CREATE TABLE applications (
	id VARCHAR(36) NOT NULL,
	job_id VARCHAR(36),
	status VARCHAR(32) NOT NULL,
	priority VARCHAR(16) NOT NULL,
	applied_date DATETIME,
	cv_version VARCHAR(128),
	cover_letter_version VARCHAR(128),
	notes TEXT,
	recruiter_name VARCHAR(256),
	recruiter_email VARCHAR(256),
	recruiter_phone VARCHAR(64),
	agency_name VARCHAR(256),
	salary_offered FLOAT,
	rejection_reason VARCHAR(512),
	agent_created BOOLEAN NOT NULL,
	approval_status VARCHAR(16) NOT NULL,
	cv_variant VARCHAR(8),
	cl_variant VARCHAR(8),
	response_received BOOLEAN NOT NULL,
	response_date DATETIME,
	is_active BOOLEAN NOT NULL,
	created_at DATETIME NOT NULL,
	updated_at DATETIME NOT NULL,
	PRIMARY KEY (id),
	FOREIGN KEY(job_id) REFERENCES job_postings (id)
);

-- table: async_jobs
CREATE TABLE async_jobs (
	id VARCHAR(36) NOT NULL,
	type VARCHAR(64) NOT NULL,
	status VARCHAR(16) NOT NULL,
	result_json TEXT,
	error TEXT,
	created_at DATETIME NOT NULL,
	updated_at DATETIME NOT NULL,
	PRIMARY KEY (id)
);

-- table: company_research
CREATE TABLE company_research (
	id VARCHAR(36) NOT NULL,
	company_name VARCHAR(256) NOT NULL,
	sector VARCHAR(128),
	website VARCHAR(512),
	description TEXT,
	recent_news JSON,
	key_products JSON,
	tech_stack_signals JSON,
	cached_at DATETIME NOT NULL,
	expires_at DATETIME NOT NULL,
	PRIMARY KEY (id)
);

-- table: company_watchlist_items
CREATE TABLE company_watchlist_items (
	id VARCHAR(36) NOT NULL,
	company_name VARCHAR(256) NOT NULL,
	company_website VARCHAR(2048),
	careers_url VARCHAR(2048) NOT NULL,
	source_type VARCHAR(64) NOT NULL,
	status VARCHAR(32) NOT NULL,
	scan_frequency VARCHAR(16) NOT NULL,
	role_keywords JSON,
	location_preferences JSON,
	remote_preference VARCHAR(16) NOT NULL,
	min_match_score FLOAT,
	last_scanned_at DATETIME,
	last_successful_scan_at DATETIME,
	last_error TEXT,
	created_at DATETIME NOT NULL,
	updated_at DATETIME NOT NULL,
	PRIMARY KEY (id)
);

-- table: cost_tracking
CREATE TABLE cost_tracking (
	id VARCHAR(36) NOT NULL,
	agent_name VARCHAR(64) NOT NULL,
	event_id VARCHAR(36),
	job_id VARCHAR(36),
	model VARCHAR(128) NOT NULL,
	tokens_in INTEGER,
	tokens_out INTEGER,
	cost_estimate FLOAT,
	currency VARCHAR(8) NOT NULL,
	created_at DATETIME NOT NULL,
	PRIMARY KEY (id),
	FOREIGN KEY(event_id) REFERENCES agent_events (id) ON DELETE SET NULL,
	FOREIGN KEY(job_id) REFERENCES job_postings (id) ON DELETE SET NULL
);

-- table: discovered_role_fingerprints
CREATE TABLE discovered_role_fingerprints (
	id VARCHAR(36) NOT NULL,
	source_url VARCHAR(2048) NOT NULL,
	normalized_company VARCHAR(256) NOT NULL,
	normalized_title VARCHAR(512) NOT NULL,
	normalized_location VARCHAR(256),
	external_job_id VARCHAR(256),
	content_hash VARCHAR(64),
	first_seen_at DATETIME NOT NULL,
	last_seen_at DATETIME NOT NULL,
	PRIMARY KEY (id),
	UNIQUE (source_url)
);

-- table: follow_up_emails
CREATE TABLE follow_up_emails (
	id VARCHAR(36) NOT NULL,
	follow_up_id VARCHAR(36),
	application_id VARCHAR(36) NOT NULL,
	email_type VARCHAR(32) NOT NULL,
	recipient_email VARCHAR(256),
	recipient_name VARCHAR(256),
	subject VARCHAR(512) NOT NULL,
	body_html TEXT NOT NULL,
	body_plain TEXT NOT NULL,
	status VARCHAR(16) NOT NULL,
	sent_via VARCHAR(16),
	sent_at DATETIME,
	opened_at DATETIME,
	generation_params TEXT,
	user_edits TEXT,
	created_at DATETIME NOT NULL,
	PRIMARY KEY (id),
	FOREIGN KEY(follow_up_id) REFERENCES follow_ups (id),
	FOREIGN KEY(application_id) REFERENCES applications (id)
);

-- table: follow_ups
CREATE TABLE follow_ups (
	id VARCHAR(36) NOT NULL,
	application_id VARCHAR(36) NOT NULL,
	due_date DATETIME NOT NULL,
	type VARCHAR(32) NOT NULL,
	note TEXT,
	completed BOOLEAN NOT NULL,
	completed_at DATETIME,
	created_at DATETIME NOT NULL,
	PRIMARY KEY (id),
	FOREIGN KEY(application_id) REFERENCES applications (id)
);

-- table: generated_document_assets
CREATE TABLE generated_document_assets (
	id VARCHAR(36) NOT NULL,
	application_id VARCHAR(36) NOT NULL,
	package_id VARCHAR(36) NOT NULL,
	source_document_id VARCHAR(36) NOT NULL,
	kind VARCHAR(32) NOT NULL,
	format VARCHAR(16) NOT NULL,
	path_or_blob_ref VARCHAR(512) NOT NULL,
	generation_status VARCHAR(32) NOT NULL,
	error_message VARCHAR(512),
	created_at DATETIME NOT NULL,
	PRIMARY KEY (id),
	FOREIGN KEY(application_id) REFERENCES applications (id) ON DELETE CASCADE,
	FOREIGN KEY(source_document_id) REFERENCES generated_documents (id) ON DELETE CASCADE
);

-- table: generated_documents
CREATE TABLE generated_documents (
	id VARCHAR(36) NOT NULL,
	application_id VARCHAR(36) NOT NULL,
	document_type VARCHAR(16) NOT NULL,
	version INTEGER NOT NULL,
	file_path VARCHAR(512),
	file_size_bytes INTEGER,
	jd_analysis_snapshot TEXT,
	tailoring_params TEXT,
	ats_score INTEGER,
	ats_details TEXT,
	variant_label VARCHAR(4),
	status VARCHAR(32) NOT NULL,
	created_at DATETIME NOT NULL,
	PRIMARY KEY (id),
	CONSTRAINT uq_doc_app_type_version UNIQUE (application_id, document_type, version),
	FOREIGN KEY(application_id) REFERENCES applications (id) ON DELETE CASCADE
);

-- table: interview_rounds
CREATE TABLE interview_rounds (
	id VARCHAR(36) NOT NULL,
	application_id VARCHAR(36) NOT NULL,
	round_number INTEGER NOT NULL,
	type VARCHAR(32) NOT NULL,
	scheduled_at DATETIME,
	duration_minutes INTEGER,
	location VARCHAR(256),
	interviewer_name VARCHAR(256),
	feedback TEXT,
	prep_notes TEXT,
	questions_asked JSON,
	status VARCHAR(32) NOT NULL,
	created_at DATETIME NOT NULL,
	updated_at DATETIME NOT NULL,
	PRIMARY KEY (id),
	FOREIGN KEY(application_id) REFERENCES applications (id)
);

-- table: interview_sessions
CREATE TABLE interview_sessions (
	id VARCHAR(36) NOT NULL,
	application_id VARCHAR(36),
	company_name VARCHAR(256) NOT NULL,
	role_title VARCHAR(256) NOT NULL,
	config JSON,
	status VARCHAR(32) NOT NULL,
	started_at DATETIME,
	completed_at DATETIME,
	overall_score FLOAT,
	feedback_summary TEXT,
	created_at DATETIME NOT NULL,
	coach_mode VARCHAR(16),
	rubric JSON,
	signals JSON,
	parent_session_id VARCHAR(36),
	focus_areas JSON,
	diagnostics JSON,
	report_json JSON,
	report_state VARCHAR(16) DEFAULT 'not_started' NOT NULL,
	report_job_id VARCHAR(36),
	report_started_at DATETIME,
	activity_version INTEGER DEFAULT 0 NOT NULL,
	PRIMARY KEY (id),
	CONSTRAINT ck_interview_sessions_report_state CHECK (report_state IN ('not_started', 'building', 'completed', 'fallback', 'failed')),
	FOREIGN KEY(application_id) REFERENCES applications (id) ON DELETE SET NULL,
	FOREIGN KEY(parent_session_id) REFERENCES interview_sessions (id) ON DELETE SET NULL
);

-- table: job_postings
CREATE TABLE job_postings (
	id VARCHAR(36) NOT NULL,
	title VARCHAR(512) NOT NULL,
	company VARCHAR(256),
	location VARCHAR(256),
	rate_text VARCHAR(128),
	rate_min FLOAT,
	rate_max FLOAT,
	currency VARCHAR(8) NOT NULL,
	ir35_status VARCHAR(32),
	legal_fields JSON,
	contract_length VARCHAR(128),
	description TEXT,
	url VARCHAR(2048) NOT NULL,
	source VARCHAR(64) NOT NULL,
	posted_at DATETIME,
	scraped_at DATETIME NOT NULL,
	skills JSON,
	employment_type VARCHAR(32) NOT NULL,
	working_pattern VARCHAR(32) NOT NULL,
	rate_type VARCHAR(16) NOT NULL,
	seniority VARCHAR(32),
	match_score FLOAT,
	match_reasons JSON,
	red_flags JSON,
	ghost_score INTEGER,
	ghost_verdict VARCHAR(16),
	ghost_signals TEXT,
	ghost_analysed_at DATETIME,
	first_seen_at DATETIME,
	times_seen INTEGER NOT NULL,
	last_seen_at DATETIME,
	needs_enrichment BOOLEAN NOT NULL,
	auto_scored BOOLEAN NOT NULL,
	auto_tailored BOOLEAN NOT NULL,
	is_active BOOLEAN NOT NULL,
	sync_status VARCHAR(32) NOT NULL,
	created_at DATETIME NOT NULL,
	updated_at DATETIME NOT NULL,
	PRIMARY KEY (id),
	UNIQUE (url)
);

-- table: job_scores
CREATE TABLE job_scores (
	id VARCHAR(36) NOT NULL,
	job_id VARCHAR(36) NOT NULL,
	overall_score FLOAT NOT NULL,
	skill_match FLOAT,
	experience_match FLOAT,
	rate_match FLOAT,
	location_match FLOAT,
	reasoning TEXT,
	scoring_method VARCHAR(20),
	keyword_matches JSON,
	keyword_misses JSON,
	fit_reasoning TEXT,
	strengths JSON,
	score_gaps JSON,
	scored_at DATETIME NOT NULL,
	PRIMARY KEY (id),
	CONSTRAINT uq_job_scores_job_id UNIQUE (job_id),
	FOREIGN KEY(job_id) REFERENCES job_postings (id)
);

-- table: onboarding_state
CREATE TABLE onboarding_state (
	id INTEGER NOT NULL,
	status VARCHAR(32) NOT NULL,
	last_completed_step VARCHAR(64),
	finalization_id VARCHAR(36),
	finalization_payload_hash VARCHAR(64),
	finalized_profile_hash VARCHAR(64),
	created_at DATETIME NOT NULL,
	updated_at DATETIME NOT NULL,
	PRIMARY KEY (id),
	CONSTRAINT ck_onboarding_state_singleton CHECK (id = 1),
	CONSTRAINT ck_onboarding_state_status CHECK (status IN ('not_started', 'in_progress', 'finalization_pending', 'complete'))
);

-- table: opportunity_scores
CREATE TABLE opportunity_scores (
	id VARCHAR(36) NOT NULL,
	job_id VARCHAR(36) NOT NULL,
	base_fit_score FLOAT NOT NULL,
	outcome_adjustment FLOAT NOT NULL,
	opportunity_score FLOAT NOT NULL,
	confidence VARCHAR(16) NOT NULL,
	raw_sample_size INTEGER NOT NULL,
	effective_sample_size FLOAT NOT NULL,
	reasons JSON NOT NULL,
	signal_contributions JSON NOT NULL,
	model_version VARCHAR(32) NOT NULL,
	calculated_at DATETIME NOT NULL,
	PRIMARY KEY (id),
	CONSTRAINT uq_opportunity_scores_job_id UNIQUE (job_id),
	FOREIGN KEY(job_id) REFERENCES job_postings (id)
);

-- table: question_bank_items
CREATE TABLE question_bank_items (
	id VARCHAR(36) NOT NULL,
	type VARCHAR(48) NOT NULL,
	question TEXT,
	title VARCHAR(256) NOT NULL,
	answer_draft TEXT NOT NULL,
	situation TEXT,
	task TEXT,
	action TEXT,
	result TEXT,
	skills JSON,
	tags JSON,
	seniority VARCHAR(64),
	role_family VARCHAR(128),
	linked_applications JSON,
	source VARCHAR(32) NOT NULL,
	confidence VARCHAR(16) NOT NULL,
	source_session_id VARCHAR(36),
	source_question_id VARCHAR(36),
	archived_at DATETIME,
	created_at DATETIME NOT NULL,
	updated_at DATETIME NOT NULL,
	PRIMARY KEY (id)
);

-- table: recruiter_contacts
CREATE TABLE recruiter_contacts (
	id VARCHAR(36) NOT NULL,
	job_id VARCHAR(36),
	company_name VARCHAR(256),
	recruiter_name VARCHAR(256),
	recruiter_title VARCHAR(256),
	email_guess VARCHAR(256),
	email_confidence FLOAT,
	linkedin_url VARCHAR(512),
	outreach_message TEXT,
	outreach_status VARCHAR(32) NOT NULL,
	created_at DATETIME NOT NULL,
	PRIMARY KEY (id),
	FOREIGN KEY(job_id) REFERENCES job_postings (id)
);

-- table: scrape_logs
CREATE TABLE scrape_logs (
	id INTEGER NOT NULL,
	source VARCHAR(64) NOT NULL,
	started_at DATETIME NOT NULL,
	finished_at DATETIME,
	jobs_found INTEGER NOT NULL,
	jobs_new INTEGER NOT NULL,
	errors INTEGER NOT NULL,
	error_details TEXT,
	PRIMARY KEY (id)
);

-- table: session_questions
CREATE TABLE session_questions (
	id VARCHAR(36) NOT NULL,
	session_id VARCHAR(36) NOT NULL,
	question_num INTEGER NOT NULL,
	text TEXT NOT NULL,
	category VARCHAR(64) NOT NULL,
	difficulty VARCHAR(32) NOT NULL,
	context TEXT,
	model_answer TEXT,
	requirement_id VARCHAR(64),
	model_answer_diagnostics JSON,
	order_in_session INTEGER NOT NULL,
	PRIMARY KEY (id),
	FOREIGN KEY(session_id) REFERENCES interview_sessions (id) ON DELETE CASCADE
);

-- table: session_recordings
CREATE TABLE session_recordings (
	id VARCHAR(36) NOT NULL,
	session_id VARCHAR(36) NOT NULL,
	question_id VARCHAR(36),
	recording_type VARCHAR(16) NOT NULL,
	transcript TEXT,
	audio_uri VARCHAR(512),
	video_uri VARCHAR(512),
	speech_metrics JSON,
	video_metrics JSON,
	evaluation_json TEXT,
	evaluation_state VARCHAR(16),
	async_job_id VARCHAR(36),
	created_at DATETIME NOT NULL,
	PRIMARY KEY (id),
	CONSTRAINT ck_session_recordings_evaluation_state CHECK (evaluation_state IS NULL OR evaluation_state IN ('pending', 'completed', 'unavailable', 'invalid', 'skipped', 'failed')),
	FOREIGN KEY(session_id) REFERENCES interview_sessions (id) ON DELETE CASCADE,
	FOREIGN KEY(question_id) REFERENCES session_questions (id) ON DELETE SET NULL
);

-- table: stories
CREATE TABLE stories (
	id VARCHAR(36) NOT NULL,
	title VARCHAR(200) NOT NULL,
	slug VARCHAR(220) NOT NULL,
	summary VARCHAR(200),
	situation TEXT,
	task TEXT,
	action TEXT,
	result TEXT,
	reflection TEXT,
	tags JSON,
	skills JSON,
	metrics JSON,
	archetype_fit JSON,
	strength_score FLOAT NOT NULL,
	times_used INTEGER NOT NULL,
	times_edited INTEGER NOT NULL,
	version INTEGER NOT NULL,
	manual_rating INTEGER,
	source_session_id VARCHAR(36),
	source_question_id VARCHAR(36),
	embedding JSON,
	is_active BOOLEAN NOT NULL,
	created_at DATETIME NOT NULL,
	updated_at DATETIME NOT NULL,
	PRIMARY KEY (id),
	UNIQUE (slug),
	FOREIGN KEY(source_session_id) REFERENCES interview_sessions (id) ON DELETE SET NULL,
	FOREIGN KEY(source_question_id) REFERENCES session_questions (id) ON DELETE SET NULL
);

-- table: story_usages
CREATE TABLE story_usages (
	id VARCHAR(36) NOT NULL,
	story_id VARCHAR(36) NOT NULL,
	session_id VARCHAR(36),
	question_id VARCHAR(36),
	match_confidence FLOAT,
	match_stage VARCHAR(20),
	used_at DATETIME NOT NULL,
	PRIMARY KEY (id),
	FOREIGN KEY(story_id) REFERENCES stories (id) ON DELETE CASCADE,
	FOREIGN KEY(session_id) REFERENCES interview_sessions (id) ON DELETE SET NULL,
	FOREIGN KEY(question_id) REFERENCES session_questions (id) ON DELETE SET NULL
);

-- table: tailoring_reviews
CREATE TABLE tailoring_reviews (
	id VARCHAR(36) NOT NULL,
	application_id VARCHAR(36) NOT NULL,
	cv_document_id VARCHAR(36),
	cl_document_id VARCHAR(36),
	review_json JSON NOT NULL,
	template_id VARCHAR(64) NOT NULL,
	variant VARCHAR(8) NOT NULL,
	created_at DATETIME NOT NULL,
	PRIMARY KEY (id),
	FOREIGN KEY(application_id) REFERENCES applications (id) ON DELETE CASCADE,
	FOREIGN KEY(cv_document_id) REFERENCES generated_documents (id) ON DELETE SET NULL,
	FOREIGN KEY(cl_document_id) REFERENCES generated_documents (id) ON DELETE SET NULL
);

-- table: watchlist_scan_runs
CREATE TABLE watchlist_scan_runs (
	id VARCHAR(36) NOT NULL,
	watchlist_item_id VARCHAR(36) NOT NULL,
	status VARCHAR(32) NOT NULL,
	started_at DATETIME,
	completed_at DATETIME,
	source_provider VARCHAR(64) NOT NULL,
	discovered_count INTEGER NOT NULL,
	new_count INTEGER NOT NULL,
	duplicate_count INTEGER NOT NULL,
	imported_count INTEGER NOT NULL,
	error_message TEXT,
	PRIMARY KEY (id),
	FOREIGN KEY(watchlist_item_id) REFERENCES company_watchlist_items (id) ON DELETE CASCADE
);
