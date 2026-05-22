"""Database seeding script — populates sample job postings for development."""
from __future__ import annotations

import asyncio
import random
import uuid
from datetime import datetime, timedelta

from .database import AsyncSessionLocal, init_db
from .models.job import JobPosting


SAMPLE_JOBS: list[dict[str, object]] = [
    {
        "title": "Senior Solutions Architect — AWS (Outside IR35)",
        "company": "FinTech Innovations Ltd",
        "location": "London, UK (Hybrid)",
        "rate_text": "£750/day",
        "rate_min": 750.0,
        "rate_max": 750.0,
        "ir35_status": "outside",
        "contract_length": "6 months",
        "description": "We need an experienced AWS Solutions Architect to lead cloud migration. Outside IR35. Ltd company preferred.",
        "source": "contractoruk",
        "skills": ["AWS", "Terraform", "Kubernetes", "Python", "Solutions Architect"],
    },
    {
        "title": "Cloud Architect — Azure (Outside IR35)",
        "company": "Global Bank PLC",
        "location": "Manchester, UK",
        "rate_text": "£700-£800/day",
        "rate_min": 700.0,
        "rate_max": 800.0,
        "ir35_status": "outside",
        "contract_length": "12 months",
        "description": "Azure cloud architect needed for greenfield financial platform. B2B contract, outside IR35.",
        "source": "reed",
        "skills": ["Azure", "Terraform", "DevOps", "CI/CD", "Solutions Architect"],
    },
    {
        "title": "Enterprise Solutions Architect",
        "company": "Consulting Partners UK",
        "location": "Remote",
        "rate_text": "£650/day",
        "rate_min": 650.0,
        "rate_max": 650.0,
        "ir35_status": "outside",
        "contract_length": "3 months",
        "description": "Enterprise architect required for digital transformation programme. TOGAF preferred. Outside IR35.",
        "source": "jobserve",
        "skills": ["TOGAF", "Solutions Architect", "Agile", "AWS", "Azure"],
    },
    {
        "title": "Technical Architect — GCP",
        "company": "Retail Tech Ltd",
        "location": "Leeds, UK",
        "rate_text": "£600-£700/day",
        "rate_min": 600.0,
        "rate_max": 700.0,
        "ir35_status": "outside",
        "contract_length": "6 months",
        "description": "GCP architect to design scalable data platform. Contract via Ltd company. Outside IR35.",
        "source": "adzuna",
        "skills": ["GCP", "Python", "Kafka", "Data Engineer", "Solutions Architect"],
    },
    {
        "title": "Infrastructure Architect (Inside IR35)",
        "company": "NHS Digital",
        "location": "Leeds, UK",
        "rate_text": "£500/day",
        "rate_min": 500.0,
        "rate_max": 500.0,
        "ir35_status": "inside",
        "contract_length": "12 months",
        "description": "Infrastructure architect for NHS cloud programme. PAYE contract, inside IR35.",
        "source": "cwjobs",
        "skills": ["AWS", "Linux", "Ansible", "Terraform"],
    },
    {
        "title": "Security Architect — SC Cleared",
        "company": "Defence Systems Ltd",
        "location": "Bristol, UK",
        "rate_text": "£800/day",
        "rate_min": 800.0,
        "rate_max": 800.0,
        "ir35_status": "outside",
        "contract_length": "6 months",
        "description": "SC cleared security architect for government project. B2B, outside IR35. SABSA or CISSP preferred.",
        "source": "jobserve",
        "skills": ["Security Architect", "SABSA", "AWS", "Azure", "Solutions Architect"],
    },
    {
        "title": "Data Architect — Databricks",
        "company": "InsurTech Startup",
        "location": "London, UK (Remote)",
        "rate_text": "£650-£750/day",
        "rate_min": 650.0,
        "rate_max": 750.0,
        "ir35_status": "outside",
        "contract_length": "6 months",
        "description": "Data architect to design modern data lakehouse. Databricks, dbt, Kafka. Ltd company, outside IR35.",
        "source": "linkedin",
        "skills": ["Data Engineer", "Python", "Kafka", "GCP", "AWS"],
    },
    {
        "title": "Solutions Architect — Microservices",
        "company": "E-Commerce Platform Co",
        "location": "Birmingham, UK",
        "rate_text": "£600/day",
        "rate_min": 600.0,
        "rate_max": 600.0,
        "ir35_status": "outside",
        "contract_length": "6 months",
        "description": "Microservices architect for re-platforming project. Java, Kubernetes, AWS. Outside IR35.",
        "source": "itjobswatch",
        "skills": ["Microservices", "Java", "Kubernetes", "AWS", "Solutions Architect"],
    },
    {
        "title": "Platform Engineer / Architect",
        "company": "Scale-up SaaS",
        "location": "Remote",
        "rate_text": "£700/day",
        "rate_min": 700.0,
        "rate_max": 700.0,
        "ir35_status": "outside",
        "contract_length": "3 months",
        "description": "Platform architect to design developer platform on K8s. Outside IR35, Ltd company.",
        "source": "contractoruk",
        "skills": ["Kubernetes", "Docker", "Terraform", "ArgoCD", "AWS"],
    },
    {
        "title": "Integration Architect — MuleSoft",
        "company": "Retail Group UK",
        "location": "London, UK",
        "rate_text": "£550-£650/day",
        "rate_min": 550.0,
        "rate_max": 650.0,
        "ir35_status": "unknown",
        "contract_length": "6 months",
        "description": "Integration architect to design MuleSoft-based API layer. Contract role.",
        "source": "reed",
        "skills": ["REST", "GraphQL", "AWS", "Solutions Architect"],
    },
    {
        "title": "Network Architect (Inside IR35)",
        "company": "Government Dept",
        "location": "London, UK",
        "rate_text": "£450/day",
        "rate_min": 450.0,
        "rate_max": 450.0,
        "ir35_status": "inside",
        "contract_length": "12 months",
        "description": "Network architect for government shared services. PAYE only, inside IR35.",
        "source": "cwjobs",
        "skills": ["Linux", "Solutions Architect"],
    },
    {
        "title": "Cloud Solutions Architect — Multi-Cloud",
        "company": "Consultancy XYZ",
        "location": "Edinburgh, UK",
        "rate_text": "£700-£850/day",
        "rate_min": 700.0,
        "rate_max": 850.0,
        "ir35_status": "outside",
        "contract_length": "6 months",
        "description": "Multi-cloud architect (AWS + Azure) for international consultancy. Outside IR35.",
        "source": "adzuna",
        "skills": ["AWS", "Azure", "Terraform", "Solutions Architect", "Cloud Architect"],
    },
    {
        "title": "DevOps Architect",
        "company": "HealthTech Ltd",
        "location": "Remote (UK)",
        "rate_text": "£600/day",
        "rate_min": 600.0,
        "rate_max": 600.0,
        "ir35_status": "outside",
        "contract_length": "6 months",
        "description": "DevOps architect to define CI/CD strategy and GitOps practices. AWS. Outside IR35.",
        "source": "jobserve",
        "skills": ["DevOps", "CI/CD", "AWS", "GitHub Actions", "Helm", "ArgoCD"],
    },
    {
        "title": "AI / ML Architect",
        "company": "AI Ventures Ltd",
        "location": "London, UK",
        "rate_text": "£900/day",
        "rate_min": 900.0,
        "rate_max": 900.0,
        "ir35_status": "outside",
        "contract_length": "3 months",
        "description": "ML platform architect to design LLM inference infrastructure. Python, AWS SageMaker. Outside IR35.",
        "source": "linkedin",
        "skills": ["Machine Learning", "AI", "LLM", "Python", "AWS", "Solutions Architect"],
    },
    {
        "title": "Serverless Architect — AWS Lambda",
        "company": "PropTech Startup",
        "location": "Remote",
        "rate_text": "£625/day",
        "rate_min": 625.0,
        "rate_max": 625.0,
        "ir35_status": "outside",
        "contract_length": "6 months",
        "description": "Architect event-driven serverless platform on AWS. Outside IR35, B2B.",
        "source": "contractoruk",
        "skills": ["Serverless", "AWS", "Python", "Solutions Architect"],
    },
    {
        "title": "Solutions Architect — Digital Transformation",
        "company": "Big Four Consultancy",
        "location": "London / Remote",
        "rate_text": "£800/day",
        "rate_min": 800.0,
        "rate_max": 800.0,
        "ir35_status": "outside",
        "contract_length": "12 months",
        "description": "Senior SA to lead digital transformation for FTSE 100 client. Outside IR35.",
        "source": "reed",
        "skills": ["Solutions Architect", "AWS", "Azure", "Agile", "TOGAF"],
    },
    {
        "title": "Kubernetes Platform Architect",
        "company": "Telco Provider",
        "location": "Glasgow, UK",
        "rate_text": "£650/day",
        "rate_min": 650.0,
        "rate_max": 650.0,
        "ir35_status": "outside",
        "contract_length": "6 months",
        "description": "K8s platform architect to design internal PaaS. Outside IR35, Ltd.",
        "source": "itjobswatch",
        "skills": ["Kubernetes", "Docker", "Helm", "ArgoCD", "AWS"],
    },
    {
        "title": "API Architect — GraphQL & REST",
        "company": "Open Banking Platform",
        "location": "London, UK (Hybrid)",
        "rate_text": "£675/day",
        "rate_min": 675.0,
        "rate_max": 675.0,
        "ir35_status": "outside",
        "contract_length": "6 months",
        "description": "Design open banking API layer using GraphQL and REST. AWS, TypeScript. Outside IR35.",
        "source": "adzuna",
        "skills": ["REST", "GraphQL", "TypeScript", "AWS", "Solutions Architect"],
    },
    {
        "title": "Big Data Architect — Spark",
        "company": "Energy Company UK",
        "location": "Manchester, UK",
        "rate_text": "£700/day",
        "rate_min": 700.0,
        "rate_max": 700.0,
        "ir35_status": "outside",
        "contract_length": "9 months",
        "description": "Data architect for smart meter data platform. Spark, Databricks, Azure. Outside IR35.",
        "source": "cwjobs",
        "skills": ["Data Engineer", "Python", "Azure", "Kafka"],
    },
    {
        "title": "Blockchain Solutions Architect",
        "company": "Fintech Blockchain Ltd",
        "location": "London, UK",
        "rate_text": "£850/day",
        "rate_min": 850.0,
        "rate_max": 850.0,
        "ir35_status": "outside",
        "contract_length": "3 months",
        "description": "Architect blockchain-based trade finance solution. AWS, Ethereum. Outside IR35.",
        "source": "jobserve",
        "skills": ["AWS", "Solutions Architect", "Python"],
    },
]


async def seed() -> None:
    """Seed the database with sample job postings for development."""
    await init_db()

    async with AsyncSessionLocal() as session:
        now = datetime.utcnow()
        count = 0

        for i, job_data in enumerate(SAMPLE_JOBS):
            job_id = str(uuid.uuid4())
            days_ago = random.randint(0, 14)
            scraped_at = now - timedelta(days=days_ago, hours=random.randint(0, 23))
            posted_at = scraped_at - timedelta(hours=random.randint(1, 24))

            job = JobPosting(
                id=job_id,
                title=str(job_data["title"]),
                company=str(job_data.get("company", "")),
                location=str(job_data.get("location", "")),
                rate_text=str(job_data.get("rate_text", "")) if job_data.get("rate_text") else None,
                rate_min=job_data.get("rate_min"),  # type: ignore[arg-type]
                rate_max=job_data.get("rate_max"),  # type: ignore[arg-type]
                currency="GBP",
                ir35_status=str(job_data.get("ir35_status", "unknown")),
                contract_length=str(job_data.get("contract_length", "")) if job_data.get("contract_length") else None,
                description=str(job_data.get("description", "")),
                url=f"https://example.com/jobs/{job_id}",
                source=str(job_data.get("source", "seed")),
                posted_at=posted_at,
                scraped_at=scraped_at,
                skills=job_data.get("skills"),  # type: ignore[arg-type]
                is_active=True,
                sync_status="pending",
                created_at=scraped_at,
                updated_at=scraped_at,
            )
            session.add(job)
            count += 1

        await session.commit()
        print(f"Seeded {count} sample jobs successfully.")


if __name__ == "__main__":
    asyncio.run(seed())
