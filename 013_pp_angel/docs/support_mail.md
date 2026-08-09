## 件名
Quota Increase Request for gpt-image-2 (Microsoft Foundry) - East US 2 - Ref: SR #2608070030001805

## 本文
Hello,

I am writing to request a quota increase for the gpt-image-2 model (Microsoft Foundry / Azure AI Foundry) in the East US 2 region.

This request was previously submitted as SR #2608070030001805 to Azure Billing and Subscription Management Support. We were advised by the support engineer (Ankit Vishwakarma) that quota increase requests for Microsoft Foundry models should be directed to this team.

Subscription details:

Subscription ID: 258b4f0d-2395-480b-924a-9ab5eefee876
Subscription name: CRS-PJ
Resource name: kinoshita-ryosuke-4406-resource
Resource group: test20251008
Region: East US 2 (eastus2)
Model / Deployment type: gpt-image-2 (OpenAI.GlobalStandard.gpt-image-2)
Current quota (subscription-level, Requests Per Minute): 4
Requested quota (Requests Per Minute): 15

Justification:

We are developing an internal business application that automatically generates PowerPoint-style presentation slides using AI-generated images. The workflow uses the gpt-image-2 model in two stages: (1) generating a small number of style/template proposal images from a text prompt, and (2) using image edit calls on that style image to produce each individual slide (typically around 10 slides per presentation) with slide-specific titles and content.

Because a single presentation requires roughly 10 image edit calls to be produced within one user session, and the user expects results within a reasonable wait time, these calls need to run concurrently rather than strictly sequentially. Our current deployment is limited to 2 requests per minute per deployment (4 RPM total at the subscription level for this model/region), which forces us to throttle concurrency heavily. As a result, generating a single 10-slide presentation takes several minutes even though only a single user is using the application at a time.

We are requesting an increase to approximately 15 requests per minute at the subscription level for this model in this region. This provides enough headroom to generate all slides of a single presentation (~10 slides) in parallel for one active user, plus a small margin for retries and for the initial style-proposal generation step.

Expected usage pattern: this is an internal productivity tool used by a single user at a time (no concurrent multi-user load), during business hours (JST). Each session generates one presentation of about 10 slides, so peak demand is a short burst of up to ~15 requests within roughly a minute, not sustained high-volume traffic.

Please let me know if any additional information is needed to process this request.

Thank you for your assistance.

Best regards,
Ryosuke Kinoshita
