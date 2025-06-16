#include <iostream>
#include <string>
#include <vector>
#include <cstdlib>
#include <map>
#include <random>
#include <nlohmann/json.hpp>

//A program that simulates a slot machine!

//A structure that include the symbols and the payout for that symbol
struct SlotMachine {
  //The symbols followed by the payout multiplier
  std::vector<std::string> symbols;
  std::map<std::string, double> payout_table;
  std::map<std::string, int> symbol_frequency;
};

//Return which machine
SlotMachine get_machine_by_type(const std::string& type) {
  if(type == "basic") {
    return SlotMachine{
      {"👾", "💀", "💅"},
      {{"👾", 2.0}, {"💀", 0.75}, {"💅", 1.0}},
      {{"👾", 3}, {"💀", 10}, {"💅", 7}}
    };
  }
  else if(type == "complex"){
    return SlotMachine{
      {"❤️", "🌑","🐝","🍋","☄️","☔️"},
      {{"❤️", 1.0}, {"🌑", 2.0}, {"🐝", 2.5}, {"🍋", 0.5}, {"☄️", 4.0}, {"☔️", 5.0}},
      {{"❤️", 9}, {"🌑", 4}, {"🐝", 3}, {"🍋", 8}, {"☄️", 2}, {"☔️", 1}}
    };
  }
  return SlotMachine{
    {"👾", "💀", "💅"},
    {{"👾", 1.5}, {"💀", 0.5}, {"💅", 1.0}},
    {{"👾", 3}, {"💀", 5}, {"💅", 4}}
  };
}

//Build out the pool of symbols incorporating frequencies
std::vector<std::string> build_pool(const SlotMachine& machine){
  std::vector<std::string> pool;
  for(const auto& [symbol, frequency] : machine.symbol_frequency){
    for (int i = 0; i < frequency; i++){
      pool.push_back(symbol);
    }
  }
  return pool;
}
//Simulate the spinning of the machine
std::vector<std::string> spin(const SlotMachine& machine, int num_slots = 3){
  std::vector<std::string> result;

  auto pool = build_pool(machine);
  
  std::mt19937 rng(std::random_device{}());
  std::uniform_int_distribution<> dist(0, pool.size() - 1);

  for(int i = 0, i < num_slots, ++i){
    result.push_back(pool[dist(rng)]);
  }

  return result;
}

//Evaluate payout multiplier
double payout_calculator(const std::vector<std::string>& spin_res, const std::map<std::string, double>& payout_table){
  std::map<std::string, int> counts;

  for(const auto& symbol : spin_res){
    counts[symbol]++;
  }

  //winner payout
  for(const auto& [symbol, count] : counts){
    if(count == spin_res.size()) {
      return payout_table.at(symbol);
    }
  }
  //loser payout
  return 0.0;
}

//A function for the bot made in Python to call
extern "C" const char* play_machine(const char* input_json){
  using json = nlohmann::json;
  static std::string result_json;
  
  try{
    auto input = json::parse(input_json);
    std::string machine_type = input["type"];

    double wager = input.contains("wager") ? input["wager"].get<double>() : 1.0;

    SlotMachine machine = get_machine_by_type(machine_type);

    auto result = spin(machine);

    double multiplier = payout_calculator(result, machine.payout_table) 
    double payout = multiplier * wager;

    json output;
    output["symbols"] = result;
    output["multiplier"] = multiplier;
    output["wager"] = wager;
    output["payout"] = payout;

    result_json = output.dump();
    return result_json.c_str();
  } catch (...) {
    result_json = R"({"error": "Invalid input or internal error."})";
    return result_json.c_str();
  }
}
