--
-- PostgreSQL database dump
--

\restrict fLfALKb3gK9QTt7gy3tkG6dVHnlNKeMNEU6GDdJVdiJ2Mf2yenQ4A2x91RmTQRP

-- Dumped from database version 18.4
-- Dumped by pg_dump version 18.4

-- Started on 2026-08-14 16:09:38

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET transaction_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

--
-- TOC entry 5 (class 2615 OID 16666)
-- Name: public; Type: SCHEMA; Schema: -; Owner: postgres
--

-- *not* creating schema, since initdb creates it


ALTER SCHEMA public OWNER TO postgres;

--
-- TOC entry 5075 (class 0 OID 0)
-- Dependencies: 5
-- Name: SCHEMA public; Type: COMMENT; Schema: -; Owner: postgres
--

COMMENT ON SCHEMA public IS '';


SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- TOC entry 220 (class 1259 OID 16673)
-- Name: admins; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.admins (
    admin_id character varying(36) NOT NULL,
    admin_name character varying(150) NOT NULL,
    admin_email character varying(30) NOT NULL,
    is_email_verified boolean,
    hash_password text NOT NULL,
    created_at timestamp with time zone,
    updated_at timestamp with time zone
);


ALTER TABLE public.admins OWNER TO postgres;

--
-- TOC entry 219 (class 1259 OID 16667)
-- Name: alembic_version; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.alembic_version (
    version_num character varying(32) NOT NULL
);


ALTER TABLE public.alembic_version OWNER TO postgres;

--
-- TOC entry 227 (class 1259 OID 16749)
-- Name: annotations; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.annotations (
    annotation_id character varying(36) NOT NULL,
    image_id character varying(36) NOT NULL,
    category_id integer NOT NULL,
    annotated_by character varying(36) NOT NULL,
    label_json_path text,
    yolo_label_path text,
    annotated_at timestamp with time zone
);


ALTER TABLE public.annotations OWNER TO postgres;

--
-- TOC entry 222 (class 1259 OID 16687)
-- Name: categories; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.categories (
    category_id integer NOT NULL,
    class_name character varying(25) NOT NULL,
    class_code integer NOT NULL,
    validated_count integer
);


ALTER TABLE public.categories OWNER TO postgres;

--
-- TOC entry 221 (class 1259 OID 16686)
-- Name: categories_category_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.categories_category_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.categories_category_id_seq OWNER TO postgres;

--
-- TOC entry 5077 (class 0 OID 0)
-- Dependencies: 221
-- Name: categories_category_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.categories_category_id_seq OWNED BY public.categories.category_id;


--
-- TOC entry 225 (class 1259 OID 16721)
-- Name: images; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.images (
    image_id character varying(36) NOT NULL,
    user_id character varying(36) NOT NULL,
    original_filename character varying(255) NOT NULL,
    temp_s3_path text,
    permanent_s3_path text,
    split_type character varying(10),
    status character varying(30),
    is_validated boolean,
    reward_given boolean,
    credits_awarded integer,
    uploaded_at timestamp with time zone,
    validated_at timestamp with time zone
);


ALTER TABLE public.images OWNER TO postgres;

--
-- TOC entry 226 (class 1259 OID 16736)
-- Name: model_versions; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.model_versions (
    model_id character varying(36) NOT NULL,
    job_id character varying(36) NOT NULL,
    version character varying(20) NOT NULL,
    is_current boolean,
    map_score double precision,
    created_at timestamp with time zone,
    updated_at timestamp with time zone
);


ALTER TABLE public.model_versions OWNER TO postgres;

--
-- TOC entry 223 (class 1259 OID 16700)
-- Name: training_jobs; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.training_jobs (
    job_id character varying(36) NOT NULL,
    version character varying(20) NOT NULL,
    class_counts json,
    status character varying(20),
    best_model_path text,
    metadata_path text,
    started_at timestamp with time zone,
    completed_at timestamp with time zone
);


ALTER TABLE public.training_jobs OWNER TO postgres;

--
-- TOC entry 224 (class 1259 OID 16709)
-- Name: users; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.users (
    user_id character varying(36) NOT NULL,
    email character varying(30) NOT NULL,
    password_hash text NOT NULL,
    full_name character varying(150),
    role character varying(20),
    is_email_verified boolean,
    verification_token text,
    reward_points integer,
    image_count integer,
    created_at timestamp with time zone,
    updated_at timestamp with time zone
);


ALTER TABLE public.users OWNER TO postgres;

--
-- TOC entry 4884 (class 2604 OID 16690)
-- Name: categories category_id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.categories ALTER COLUMN category_id SET DEFAULT nextval('public.categories_category_id_seq'::regclass);


--
-- TOC entry 5062 (class 0 OID 16673)
-- Dependencies: 220
-- Data for Name: admins; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.admins (admin_id, admin_name, admin_email, is_email_verified, hash_password, created_at, updated_at) FROM stdin;
\.


--
-- TOC entry 5061 (class 0 OID 16667)
-- Dependencies: 219
-- Data for Name: alembic_version; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.alembic_version (version_num) FROM stdin;
067a102509dc
\.


--
-- TOC entry 5069 (class 0 OID 16749)
-- Dependencies: 227
-- Data for Name: annotations; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.annotations (annotation_id, image_id, category_id, annotated_by, label_json_path, yolo_label_path, annotated_at) FROM stdin;
\.


--
-- TOC entry 5064 (class 0 OID 16687)
-- Dependencies: 222
-- Data for Name: categories; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.categories (category_id, class_name, class_code, validated_count) FROM stdin;
\.


--
-- TOC entry 5067 (class 0 OID 16721)
-- Dependencies: 225
-- Data for Name: images; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.images (image_id, user_id, original_filename, temp_s3_path, permanent_s3_path, split_type, status, is_validated, reward_given, credits_awarded, uploaded_at, validated_at) FROM stdin;
\.


--
-- TOC entry 5068 (class 0 OID 16736)
-- Dependencies: 226
-- Data for Name: model_versions; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.model_versions (model_id, job_id, version, is_current, map_score, created_at, updated_at) FROM stdin;
\.


--
-- TOC entry 5065 (class 0 OID 16700)
-- Dependencies: 223
-- Data for Name: training_jobs; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.training_jobs (job_id, version, class_counts, status, best_model_path, metadata_path, started_at, completed_at) FROM stdin;
\.


--
-- TOC entry 5066 (class 0 OID 16709)
-- Dependencies: 224
-- Data for Name: users; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.users (user_id, email, password_hash, full_name, role, is_email_verified, verification_token, reward_points, image_count, created_at, updated_at) FROM stdin;
\.


--
-- TOC entry 5078 (class 0 OID 0)
-- Dependencies: 221
-- Name: categories_category_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.categories_category_id_seq', 1, false);


--
-- TOC entry 4888 (class 2606 OID 16685)
-- Name: admins admins_admin_email_key; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.admins
    ADD CONSTRAINT admins_admin_email_key UNIQUE (admin_email);


--
-- TOC entry 4890 (class 2606 OID 16683)
-- Name: admins admins_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.admins
    ADD CONSTRAINT admins_pkey PRIMARY KEY (admin_id);


--
-- TOC entry 4886 (class 2606 OID 16672)
-- Name: alembic_version alembic_version_pkc; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.alembic_version
    ADD CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num);


--
-- TOC entry 4908 (class 2606 OID 16759)
-- Name: annotations annotations_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.annotations
    ADD CONSTRAINT annotations_pkey PRIMARY KEY (annotation_id);


--
-- TOC entry 4892 (class 2606 OID 16697)
-- Name: categories categories_class_code_key; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.categories
    ADD CONSTRAINT categories_class_code_key UNIQUE (class_code);


--
-- TOC entry 4894 (class 2606 OID 16699)
-- Name: categories categories_class_name_key; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.categories
    ADD CONSTRAINT categories_class_name_key UNIQUE (class_name);


--
-- TOC entry 4896 (class 2606 OID 16695)
-- Name: categories categories_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.categories
    ADD CONSTRAINT categories_pkey PRIMARY KEY (category_id);


--
-- TOC entry 4904 (class 2606 OID 16730)
-- Name: images images_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.images
    ADD CONSTRAINT images_pkey PRIMARY KEY (image_id);


--
-- TOC entry 4906 (class 2606 OID 16743)
-- Name: model_versions model_versions_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.model_versions
    ADD CONSTRAINT model_versions_pkey PRIMARY KEY (model_id);


--
-- TOC entry 4898 (class 2606 OID 16708)
-- Name: training_jobs training_jobs_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.training_jobs
    ADD CONSTRAINT training_jobs_pkey PRIMARY KEY (job_id);


--
-- TOC entry 4900 (class 2606 OID 16720)
-- Name: users users_email_key; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_email_key UNIQUE (email);


--
-- TOC entry 4902 (class 2606 OID 16718)
-- Name: users users_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_pkey PRIMARY KEY (user_id);


--
-- TOC entry 4911 (class 2606 OID 16760)
-- Name: annotations annotations_annotated_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.annotations
    ADD CONSTRAINT annotations_annotated_by_fkey FOREIGN KEY (annotated_by) REFERENCES public.users(user_id);


--
-- TOC entry 4912 (class 2606 OID 16765)
-- Name: annotations annotations_category_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.annotations
    ADD CONSTRAINT annotations_category_id_fkey FOREIGN KEY (category_id) REFERENCES public.categories(category_id);


--
-- TOC entry 4913 (class 2606 OID 16770)
-- Name: annotations annotations_image_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.annotations
    ADD CONSTRAINT annotations_image_id_fkey FOREIGN KEY (image_id) REFERENCES public.images(image_id);


--
-- TOC entry 4909 (class 2606 OID 16731)
-- Name: images images_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.images
    ADD CONSTRAINT images_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(user_id);


--
-- TOC entry 4910 (class 2606 OID 16744)
-- Name: model_versions model_versions_job_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.model_versions
    ADD CONSTRAINT model_versions_job_id_fkey FOREIGN KEY (job_id) REFERENCES public.training_jobs(job_id);


--
-- TOC entry 5076 (class 0 OID 0)
-- Dependencies: 5
-- Name: SCHEMA public; Type: ACL; Schema: -; Owner: postgres
--

REVOKE USAGE ON SCHEMA public FROM PUBLIC;
GRANT ALL ON SCHEMA public TO PUBLIC;


-- Completed on 2026-08-14 16:09:39

--
-- PostgreSQL database dump complete
--

\unrestrict fLfALKb3gK9QTt7gy3tkG6dVHnlNKeMNEU6GDdJVdiJ2Mf2yenQ4A2x91RmTQRP

