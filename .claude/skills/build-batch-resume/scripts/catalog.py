"""Keyword catalog for tailoring: term -> (posting regex, category).

The catalog is generic. Which terms the candidate HAS is decided per candidate (tailor.candidate_terms):
a tool counts when it appears in the resume content's skills, stack lines or the skills inventory's "used" table;
a concept counts when it appears anywhere in the resume content. Every other catalog term a posting asks for is a
GAP: reported, never added. Candidates add or fix patterns with "keyword_aliases" in resume_content.json.

Categories map to skills groups (a group's "category" in resume_content.json) so an inventory tool lands on the
right Skills line. "concept" terms are domains, practices and soft skills: matched and reported, never boosted,
never in a headline.
"""

# term: (regex, category)
CATALOG = {
    # languages
    "TypeScript": (r"typescript|\bts\b", "languages"), "JavaScript": (r"javascript|(?<![.\w])js\b", "languages"),
    "Python": (r"python", "languages"), "SQL": (r"\bsql\b", "languages"),
    "Go": (r"golang|(?-i:\bGo\b)(?! (from|to|above|beyond|live|deep|further))", "languages"),
    "Rust": (r"\brust\b", "languages"), "Java": (r"\bjava\b(?!script)", "languages"), "Kotlin": (r"kotlin", "languages"),
    "C++": (r"c\+\+", "languages"), "C#/.NET": (r"c#|\.net\b", "languages"), "Ruby/Rails": (r"\bruby\b|\brails\b", "languages"),
    "PHP": (r"\bphp\b", "languages"), "Scala": (r"scala\b", "languages"), "Elixir": (r"elixir", "languages"),
    "Swift/iOS": (r"\bswift\b|\bios\b", "frontend"), "Android": (r"android", "frontend"),
    # frontend
    "React": (r"react(?![ -]?native)", "frontend"), "Next.js": (r"next\.?js", "frontend"), "Redux": (r"redux", "frontend"),
    "React Query": (r"react query|tanstack", "frontend"), "Tailwind CSS": (r"tailwind", "frontend"),
    "React Native": (r"react[ -]?native", "frontend"), "Flutter": (r"flutter", "frontend"), "Vue": (r"\bvue", "frontend"),
    "Angular": (r"angular", "frontend"), "Svelte": (r"svelte", "frontend"), "Electron": (r"\belectron(\.js)?\b", "frontend"),
    "Figma": (r"figma", "frontend"), "Webpack/Vite": (r"webpack|\bvite\b", "frontend"), "Storybook": (r"storybook", "frontend"),
    "HTML5": (r"\bhtml5?\b", "frontend"), "CSS3": (r"\bcss3?\b", "frontend"),
    # backend
    "Node.js": (r"node\.?js|\bnode\b", "backend"),
    "Express.js": (r"express\.?js|\bexpress\b(?=\s*(/|,|and|&|\()?\s*(node|nest))|"
                   r"(node(\.?js)?|nest(\.?js)?)\s*(/|,|and|&|\()\s*express\b", "backend"),
    "NestJS": (r"nest\.?js", "backend"), "FastAPI": (r"fastapi", "backend"), "Flask": (r"flask", "backend"),
    "Django": (r"django", "backend"), "Pydantic": (r"pydantic", "backend"), "Prisma": (r"prisma", "backend"),
    "GraphQL": (r"graphql", "backend"), "REST APIs": (r"(?-i:\bREST(ful)?\b)|\brestful\b", "backend"),
    "gRPC": (r"grpc", "backend"), "WebSockets": (r"websocket", "backend"), "webhooks": (r"webhook", "backend"),
    "OAuth 2.0": (r"oauth", "backend"), "RBAC": (r"rbac|role-based access", "backend"),
    "Temporal": (r"\btemporal\b", "backend"), "Salesforce integration": (r"salesforce", "backend"),
    "Twilio": (r"twilio", "backend"),
    # data
    "PostgreSQL": (r"postgres", "data"), "MongoDB": (r"mongo", "data"), "MSSQL": (r"mssql|sql server", "data"),
    "MySQL": (r"mysql", "data"), "Redis": (r"redis", "data"), "Kafka": (r"kafka", "data"),
    "DynamoDB": (r"dynamo", "data"), "Elasticsearch": (r"elasticsearch|opensearch", "data"),
    "ClickHouse": (r"clickhouse", "data"), "Snowflake": (r"snowflake", "data"),
    "Spark": (r"(?-i:\bSpark\b)(?! Capital)|pyspark|apache spark", "data"), "Airflow": (r"airflow", "data"),
    "dbt": (r"\bdbt\b", "data"), "Supabase": (r"supabase", "data"), "Firebase": (r"firebase", "data"),
    "SQS/SNS": (r"\bsqs\b|\bsns\b", "data"), "Neo4j": (r"neo4j|graph database|graph db", "data"),
    "vector databases": (r"vector (db|database|store|search)|pgvector|pinecone", "data"),
    # cloud and devops
    "AWS": (r"\baws\b|amazon web services", "cloud"), "Azure": (r"azure", "cloud"), "GCP": (r"\bgcp\b|google cloud", "cloud"),
    "Vercel": (r"vercel", "cloud"), "Docker": (r"docker|container", "cloud"),
    "Kubernetes": (r"kubernetes|\bk8s\b", "cloud"), "Terraform": (r"terraform", "cloud"),
    "CI/CD": (r"ci/cd|continuous integration|github actions", "cloud"), "AWS Lambda": (r"lambda|serverless", "cloud"),
    "Amazon S3": (r"\bs3\b", "cloud"), "Amazon ECS/EKS": (r"\becs\b|\beks\b", "cloud"),
    "OpenTelemetry": (r"opentelemetry|\botel\b", "cloud"), "Datadog": (r"datadog", "cloud"),
    "Linux": (r"\blinux\b|unix", "cloud"), "Git": (r"\bgit\b|github", "cloud"),
    # testing
    "Jest": (r"\bjest\b", "testing"), "Playwright": (r"playwright", "testing"), "Cypress": (r"cypress", "testing"),
    "TDD": (r"\btdd\b|test-driven", "testing"), "testing": (r"\btesting\b|unit test|integration test", "concept"),
    # architecture
    "microservices": (r"microservice", "concept"), "distributed systems": (r"distributed system", "concept"),
    "event-driven": (r"event[- ]driven", "concept"), "multi-tenant SaaS": (r"multi-?tenant", "concept"),
    "system design": (r"system design|architect", "concept"), "OWASP": (r"owasp|security best", "concept"),
    # AI
    "OpenAI": (r"openai|gpt", "ai"), "Anthropic Claude": (r"anthropic|claude", "ai"), "LangChain": (r"langchain", "ai"),
    "LangGraph": (r"langgraph", "ai"), "MCP": (r"\bmcp\b|model context protocol", "ai"),
    "RAG": (r"\brag\b|retrieval[- ]augmented|retrieval", "ai"), "embeddings": (r"embedding", "ai"),
    "prompt engineering": (r"prompt", "concept"), "LLMs": (r"\bllms?\b|large language model|generative ai|genai|gen ai", "concept"),
    "AI agents": (r"\bagents?\b|agentic", "concept"), "tool calling": (r"tool[- ]?(calling|use)|function calling", "ai"),
    "OCR": (r"\bocr\b", "ai"), "evals": (r"\bevals?\b|evaluation", "concept"), "Langfuse": (r"langfuse", "ai"),
    "n8n": (r"\bn8n\b", "ai"), "AWS Bedrock": (r"bedrock", "ai"), "PyTorch": (r"pytorch", "ai"),
    "TensorFlow": (r"tensorflow", "ai"),
    "AI coding tools": (r"claude code|\bcodex\b|(?-i:\bCursor\b)|copilot|ai[- ]assisted (coding|development|engineering)|"
                        r"ai coding (tools?|assistants?)|agentic (coding|development) tools?", "ai"),
    # concepts, domains and soft skills (never boosted, never in a headline)
    "model training/fine-tuning": (r"fine-?tun|model training|train(ing)? models", "concept"),
    "CUDA/GPU": (r"cuda|\bgpu", "concept"), "HIPAA": (r"hipaa", "concept"), "FHIR": (r"fhir", "concept"),
    "healthcare": (r"healthcare|health care|clinical|clinician|patient", "concept"),
    "embedded/firmware": (r"firmware|embedded (systems?|software|c\b|linux|devices?)", "concept"),
    "robotics": (r"robotic|\bros\b", "concept"), "security clearance": (r"clearance", "concept"),
    "compilers": (r"compiler", "concept"), "workflow automation": (r"automation|automate", "concept"),
    "data visualization": (r"visuali[sz]", "concept"), "3D": (r"\b3d\b|point cloud", "concept"),
    "full-stack": (r"full[- ]?stack", "concept"), "frontend": (r"front[- ]?end", "concept"),
    "backend": (r"back[- ]?end", "concept"), "leadership": (r"\blead(ing|ership)?\b|mentor", "concept"),
    "customer-facing": (r"customer|client[- ]facing|stakeholder", "concept"),
    "product engineering": (r"product engineer|product-minded|product sense|ownership", "concept"),
    "startup": (r"startup|early[- ]stage|0 ?(to|->) ?1|zero to one", "concept"), "Agile": (r"agile|scrum", "concept"),
}

# Concepts a candidate can only "have" with evidence in their content (matched against all resume text).
CONCEPT = {k for k, (_, c) in CATALOG.items() if c == "concept"}

# Tools that are real requirements but read badly as headline keywords.
NO_HEADLINE = {"CI/CD", "Docker", "REST APIs", "webhooks", "OAuth 2.0", "Jest", "Playwright", "Redux", "React Query",
               "Tailwind CSS", "WebSockets", "SQL", "JavaScript", "Git", "HTML5", "CSS3", "Linux", "OCR", "Langfuse", "n8n",
               "RBAC", "TDD"}

# Exact-spelling counters for the finished resume (the loose posting regex would over-count).
COUNT_RX = {"REST APIs": r"\bREST(ful)?\b", "LLMs": r"\bLLMs?\b|large language model", "AI agents": r"\bagents?\b|agentic",
            "tool calling": r"tool[- ]calling", "vector databases": r"vector database", "CI/CD": r"\bCI/CD\b",
            "Docker": r"\bDocker\b", "testing": r"\btesting\b", "evals": r"\bevals?\b", "RAG": r"\bRAG\b",
            "React": r"\bReact(JS|\.js)?\b(?! Query| Native)", "JavaScript": r"\bJavaScript\b",
            "Node.js": r"\bNode(\.js|JS)?\b", "PostgreSQL": r"\bPostgres(QL)?\b", "embeddings": r"\bembeddings?\b",
            "microservices": r"\bmicroservices?\b", "OpenAI": r"\bOpenAI\b", "Anthropic Claude": r"\bClaude\b",
            "MCP": r"\bMCP\b", "OAuth 2.0": r"\bOAuth\b", "NestJS": r"\bNest\.?JS\b", "Go": r"\bGo(lang)?\b"}

# Resume spelling -> posting variants. The posting's most frequent variant wins and is used everywhere.
SPELL = {
    "React": [("ReactJS", r"\breactjs\b"), ("React.js", r"\breact\.js\b")],
    "Node.js": [("NodeJS", r"\bnodejs\b"), ("Node", r"(?-i:\bNode\b)(?![.]\w|JS)")],
    "Next.js": [("NextJS", r"\bnextjs\b")],
    "PostgreSQL": [("Postgres", r"\bpostgres\b(?!ql)")],
    "Express.js": [("ExpressJS", r"\bexpressjs\b")],
    "NestJS": [("Nest.js", r"\bnest\.js\b")],
    "MongoDB": [("Mongo", r"\bmongo\b(?!db)")],
}
SPELL_GUARD = {"React": r"(?! Query| Native)"}   # never rewrite these compounds

# Acronym on the resume -> (posting long-form regex, expansion used once on the Skills line)
ACRONYM = {
    "CI/CD": (r"continuous (integration|delivery|deployment)", "CI/CD (continuous integration and delivery)"),
    "RAG": (r"retrieval[- ]augmented", "retrieval-augmented generation (RAG)"),
    "MCP": (r"model context protocol", "Model Context Protocol (MCP)"),
    "RBAC": (r"role[- ]based access", "role-based access control (RBAC)"),
    "TDD": (r"test[- ]driven", "test-driven development (TDD)"),
    "OCR": (r"optical character", "optical character recognition (OCR)"),
}

DISPLAY = {"CI/CD": "CI/CD pipelines"}   # summary-closer wording when the Skills term carries a vendor prefix
