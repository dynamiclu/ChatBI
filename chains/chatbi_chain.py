from langchain.prompts import PromptTemplate, ChatPromptTemplate, HumanMessagePromptTemplate
from langchain.output_parsers import StructuredOutputParser, ResponseSchema
from langchain.chains import RetrievalQA, LLMChain
from common.log import logger
from common.llm_output import StructLLMOutput
from configs.config import *
from knowledge.source_service import SourceService
from models.llm_chatglm import ChatGLM
from models.llm_baichuan import LLMBaiChuan
from models.llm_tongyi import LLMTongyi
import datetime

time_today = datetime.date.today()

class ChatBiChain:
    llm: object = None
    service: object = None
    llm_out: object = None
    top_k: int = LLM_TOP_K
    llm_model: str
    his_query: str

    def init_cfg(self,
                 llm_model: str = LLM_MODEL_CHAT_GLM,
                 embedding_model: str = EMBEDDING_MODEL_DEFAULT,
                 llm_history_len=LLM_HISTORY_LEN,
                 top_k=LLM_TOP_K
                 ):
        self.init_mode(llm_model, llm_history_len)
        self.service = SourceService(embedding_model, LOCAL_EMBEDDING_DEVICE)
        self.llm_out = StructLLMOutput()
        self.his_query = ""
        self.top_k = top_k
        logger.info("--" * 30 + "ChatBiChain init " + "--" * 30)

    def init_mode(self, llm_model: str = LLM_MODEL_CHAT_GLM, llm_history_len: str = LLM_HISTORY_LEN):
        self.llm_model = llm_model
        if llm_model == LLM_MODEL_CHAT_GLM:
            self.llm = ChatGLM()
            self.llm.load_model(model_name_or_path=llm_model_dict[LLM_MODEL_CHAT_GLM],
                                llm_device=LOCAL_LLM_DEVICE)
            self.llm.history_len = llm_history_len
        elif llm_model == LLM_MODEL_BAICHUAN:
            self.llm = LLMBaiChuan()
        elif llm_model == LLM_MODEL_QIANWEN:
            self.llm = LLMTongyi()

    def run_answer(self, query: object, vs_path: str = VECTOR_STORE_PATH, chat_history: str = "", top_k=VECTOR_SEARCH_TOP_K):
        result = self.get_answer(query, vs_path, top_k)
        result = self.llm_out.out_json(result)
        return result

    def get_answer(self, query: object, vs_path: str = VECTOR_STORE_PATH, top_k=VECTOR_SEARCH_TOP_K):
        response_schemas = [
            ResponseSchema(name="data_indicators", description="数据指标: 如 PV、UV"),
            ResponseSchema(name="operator_type", description="计算类型: 明细，求和，最大值，最小值，平均值"),
            ResponseSchema(name="time_type", description="时间类型: 天、周、月、小时"),
            ResponseSchema(name="dimensions", description="维度"),
            ResponseSchema(name="filters", description="过滤条件"),
            ResponseSchema(name="filter_type", description="过滤条件类型：大于，等于，小于，范围"),
            ResponseSchema(name="date_range", description="日期范围,需按当前日期计算，假如当前日期为：2023-12-01，问 过去三个月或近几个月，则输出2023-09-01，2023-11-30；问过去一个月或上个月，则输出2023-11-01，2023-11-30；问八月或8月，则输出2023-08-01，2023-08-31；"),
            ResponseSchema(name="compare_type", description="比较类型：无，同比，环比")
        ]
        output_parser = StructuredOutputParser.from_response_schemas(response_schemas)
        format_instructions = output_parser.get_format_instructions(only_json=False)
        prompt = ChatPromptTemplate(
            messages=[
                HumanMessagePromptTemplate.from_template(
                    "从问题中抽取准确的信息，若不匹配，返回空，去掉description，\n{format_instructions} \n 当前日期:%s  \n 已知内容:{context}  \n 问题：{question}" % time_today
                )
            ],
            input_variables=["context", "question"],
            partial_variables={"format_instructions": format_instructions}
        )
        vector_store = self.service.load_vector_store(vs_path)
        knowledge_chain = RetrievalQA.from_llm(
            llm=self.llm,
            retriever=vector_store.as_retriever(search_kwargs={"k": top_k}),
            prompt=prompt
        )
        knowledge_chain.combine_documents_chain.document_prompt = PromptTemplate(
            input_variables=["page_content"], template="{page_content}"
        )
        knowledge_chain.return_source_documents = True
        result_dict = {}
        try:
            result_dict = knowledge_chain({"query": query})
        except Exception as e:
            logger.error(e)
            result_dict["result"] = "sorry，LLM model (%s) is fail，wait a minute..." % self.llm_model
        return result_dict
