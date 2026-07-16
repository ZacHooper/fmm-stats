fn byte_chunk_to_hex(chunk: List[SIMD[DType.uint8, 1]]) -> String:
    var chunk_size = len(chunk)
    var hex_chunk: String = ""
    for i in range(chunk_size):
        var hex_value = hex(int(chunk[i]), prefix="")
        # Pad the hex value with a leading zero if it's only one character long
        if len(hex_value) == 1:
            hex_value = "0" + hex_value
        hex_chunk += hex_value
    return hex_chunk


fn pretty_print_hex(hex_string: String) -> String:
    """Every byte add a space. Every 4 bytes add 3 spaces."""
    var pretty_hex: String = ""
    for i in range(len(hex_string)):
        pretty_hex += hex_string[i]
        if (i + 1) % 2 == 0:
            pretty_hex += " "
        if (i + 1) % 8 == 0:
            pretty_hex += "   "
    return pretty_hex


fn read_bytes_to_string(file: FileHandle, length: Int) raises -> String:
    var bytes = file.read_bytes(length)
    var string: String = ""
    for i in bytes:
        string += chr(int(i[]))
    return string


fn string_to_hex(value: String) -> String:
    var hex_string: String = ""
    for i in value:
        hex_string += hex(ord(i))[2:]
    return hex_string


fn hex_to_little_endian(value: String) -> String:
    # Ensure the hex string has an even length
    var padded_value: String = value
    if len(value) % 2 != 0:
        padded_value = "0" + value

    # Reverse the hex string in pairs
    var reversed_value: String = ""
    for i in range(0, len(padded_value), 2):
        reversed_value = padded_value[i : i + 2] + reversed_value

    return reversed_value


fn little_endian_to_hex(value: String) -> String:
    # Reverse the hex string in pairs
    var reversed_value: String = ""
    for i in range(0, len(value), 2):
        reversed_value = value[i : i + 2] + reversed_value

    # Remove any leading zeros
    var index = 0
    for i in range(0, len(reversed_value)):
        if reversed_value[i] != "0":
            index = i
            break

    return reversed_value[index:]


fn find_hex_in_file(
    savefile: FileHandle,
    target_hex: String,
    chunk_size: Int = 4096,
) raises -> Int:
    """See if either of the two hex strings are in the same chunk in the file. Helpful to find IDs of two different things together. Eg Player TID and Team TID.
    Returns the position of the chunk in the file where the hex strings are found.
    """
    var lower_target_hex = target_hex.lower()

    var position = 0
    while chunk := savefile.read_bytes(chunk_size):
        if position % 1000000 == 0:
            print(position)
        var hex_chunk = byte_chunk_to_hex(chunk)
        var chunk_position = hex_chunk.find(lower_target_hex)
        if chunk_position != -1:
            print(
                "Found "
                + lower_target_hex
                + " at position "
                + str(position + chunk_position)
            )
            # print("Hex chunk: " + pretty_print_hex(hex_chunk))
            print("Hex chunk length: " + str(len(hex_chunk)))
            print(
                "Sub hex chunk: "
                + pretty_print_hex(
                    hex_chunk[
                        chunk_position : chunk_position + len(lower_target_hex)
                    ]
                )
            )
            return position + chunk_position
        position += chunk_size

    print(lower_target_hex + " not found in the file.")
    return -1


@value
struct PlayerStat:
    var tid: String
    var team_pos_order: Int
    var assists: Int
    var condition: Int
    var crosses_attempted: Int
    var crosses_completed: Int
    var dribbles: Int
    var goals: Int
    var headers_attempted: Int
    var headers_won: Int
    var interceptions: Int
    var sub_on_min: Int
    var sub_off_min: Int
    var mistakes: Int
    var mistakes_to_goal: Int
    var passes_attempted: Int
    var passes_completed: Int
    var key_passes: Int
    var sid: String
    var rating: Int
    var shots_attempted: Int
    var shots_on_target: Int
    var tackles_attempted: Int
    var tackles_won: Int

    fn __init__(
        inout self,
        tid: String,
        team_pos_order: Int,
        assists: Int,
        condition: Int,
        crosses_attempted: Int,
        crosses_completed: Int,
        dribbles: Int,
        goals: Int,
        headers_attempted: Int,
        headers_won: Int,
        interceptions: Int,
        sub_on_min: Int,
        sub_off_min: Int,
        mistakes: Int,
        mistakes_to_goal: Int,
        passes_attempted: Int,
        passes_completed: Int,
        key_passes: Int,
        sid: String,
        rating: Int,
        shots_attempted: Int,
        shots_on_target: Int,
        tackles_attempted: Int,
        tackles_won: Int,
    ) raises:
        self.tid = tid
        self.team_pos_order = team_pos_order
        self.assists = assists
        self.condition = condition
        self.crosses_attempted = crosses_attempted
        self.crosses_completed = crosses_completed
        self.dribbles = dribbles
        self.goals = goals
        self.headers_attempted = headers_attempted
        self.headers_won = headers_won
        self.interceptions = interceptions
        self.sub_on_min = sub_on_min
        self.sub_off_min = sub_off_min
        self.mistakes = mistakes
        self.mistakes_to_goal = mistakes_to_goal
        self.passes_attempted = passes_attempted
        self.passes_completed = passes_completed
        self.key_passes = key_passes
        self.sid = sid
        self.rating = rating
        self.shots_attempted = shots_attempted
        self.shots_on_target = shots_on_target
        self.tackles_attempted = tackles_attempted
        self.tackles_won = tackles_won

    fn __init__(inout self, bytes: List[SIMD[DType.uint8, 1]]) raises:
        self.tid = byte_chunk_to_hex(bytes[42:46])
        self.team_pos_order = int(bytes[41])
        self.assists = int(bytes[0])
        self.condition = int(bytes[3])
        self.crosses_attempted = int(bytes[4])
        self.crosses_completed = int(bytes[5])
        self.dribbles = int(bytes[8])
        self.goals = int(bytes[10])
        self.headers_attempted = int(bytes[11])
        self.headers_won = int(bytes[12])
        self.interceptions = int(bytes[16])
        self.sub_on_min = int(bytes[19])
        self.sub_off_min = int(bytes[21])
        self.mistakes = int(bytes[22])
        self.mistakes_to_goal = int(bytes[23])
        self.passes_attempted = int(bytes[25])
        self.passes_completed = int(bytes[26])
        self.key_passes = int(bytes[27])
        self.sid = byte_chunk_to_hex(bytes[28:30])
        self.rating = int(bytes[32])
        self.shots_attempted = int(bytes[35])
        self.shots_on_target = int(bytes[36])
        self.tackles_attempted = int(bytes[48])
        self.tackles_won = int(bytes[49])

    fn print(self):
        print("TID: ", self.tid)
        print("Team Pos Order: ", self.team_pos_order)
        print("Assists: ", self.assists)
        print("Condition: ", self.condition)
        print("Crosses Attempted: ", self.crosses_attempted)
        print("Crosses Completed: ", self.crosses_completed)
        print("Dribbles: ", self.dribbles)
        print("Goals: ", self.goals)
        print("Headers Attempted: ", self.headers_attempted)
        print("Headers Won: ", self.headers_won)
        print("Interceptions: ", self.interceptions)
        print("Sub On Min: ", self.sub_on_min)
        print("Sub Off Min: ", self.sub_off_min)
        print("Mistakes: ", self.mistakes)
        print("Mistakes to Goal: ", self.mistakes_to_goal)
        print("Passes Attempted: ", self.passes_attempted)
        print("Passes Completed: ", self.passes_completed)
        print("Key Passes: ", self.key_passes)
        print("SID: ", self.sid)
        print("Rating: ", self.rating)
        print("Shots Attempted: ", self.shots_attempted)
        print("Shots on Target: ", self.shots_on_target)
        print("Tackles Attempted: ", self.tackles_attempted)
        print("Tackles Won: ", self.tackles_won)


fn main() raises:
    print("Reading save file...")
    var savefile = open("CQN - 24-25", "r")
    var offset = 72256689  # actual start
    # var offset = 72572174  # Player Stat start (Aber v CQN)
    _ = savefile.seek(offset)

    # Next 18 Bytes are basic game stats: 2E048C07 85005D01 0A042631 0001083D 0000
    # us / them / leagua / ????

    # THen loops through match events with FFFFFFFF FFFFFFFF delimeter until we see 2E048C07 again.
    # Then we get 53 bytes of more match stats. This is the important section as it tells us who is home and who is away.
    # 2E048C07 8500012E 048C075D 01E70722 03000000 0C01010D 004B000C 00FFFF10 003D0017 00FFFF00 00000000 00FFFF0E 00450011 00
    # teams    league home away
    # So above we were home. If 8c07 were home the start would read: 2E048C07 8500018C 072E04...
    # Then we get more match events with FFFFFFFF FFFFFFFF delimeter. This runs until a long 688 FFFFFFF block.
    # We need to skip until we see bytes that aren't FF or 00.
    # Looks like there is 77 bytes up till the first player stat block

    # Player Stat blocks are 54 bytes long

    # delimeter equals FFFFFFFF FFFFFFFF
    var delimeter: Int = 8
    # var match_delimiter = "242255150A000000212255150A000000212255150A000000212255150A000000212255150A000000212255150A000000212255150A000000212255150A000000212255150A000000212255150A000000212255150A00000012121212121212121212"
    var match_delimiter = "24225515"

    offset_1 = find_hex_in_file(savefile, match_delimiter, 4096)
    print(offset + offset_1)

    # Check if 600 bytes ahead of offset is some combination of 'FF' or '00'
    _ = savefile.seek(offset_1)
    offset_2 = find_hex_in_file(savefile, "FFFFFFFFFFFFFFFF", 600)
    print(offset + offset_1 + offset_2)

    return
    var num_players = 18
    for i in range(num_players):
        _ = savefile.seek(offset + (i * 54) + (i * delimeter))
        var raw_player = savefile.read_bytes(54)
        print(pretty_print_hex(byte_chunk_to_hex(raw_player)))
        var pt = PlayerStat(raw_player)
        pt.print()

    # var raw_player = savefile.read_bytes(54)
    # print(byte_chunk_to_hex(raw_player))
    # # 00 00 00 60 | 00 00 40 11 | 00000000 00521100 00FFFFFF FFFF0000 0F1C1401 04260000 08000000 000D0000 00017533 00008025 000000D7 0C00
    # # Ass ?? ?? Con | CrACrC???? | Dri??GoalsHeA | HeW?????? | Int....SubOnMin | ..SubOffMin Mis MiG | ?? PaA PaC Key | statsID? ?? ?? | Rat ?? ?? ShA | ShO ?? ?? ?? | ?? TeamPosOrder | TID |  ?? ??       TaA TaW FFIfSubbed? ?? ?? ?? |
    # var pt = PlayerStat(raw_player)
    # pt.print()

    # _ = savefile.seek(offset + 54 + delimeter)
    # raw_player = savefile.read_bytes(54)
    # print(byte_chunk_to_hex(raw_player))
    # var pt2 = PlayerStat(raw_player)
    # pt2.print()

    # 0000005803015d0f0200000000160f0003ffffffff47 01 000a090401 9c61 00000700000200 20 0000000a8a76000060220000ffa70c00 - Floody
    # 0000005e0000d605000000010103060000ffff47ffff 01 0009080500 a900 00000600000000 22 00000012650d0000b824000009c90000 - Leeson

    # 0100004e0000720f00000208023b0f0000ffffffff47 00 000a090802 8b5d 00000a00000502 1e 0000000b0f720000781e0000ff4d0a00 - Reeves
    # 0000005f00000905000000010063050000ffff47ffff 00 0012010100 4376 00000600000000 26 0000000c5c8d00001c2500000acd0100 - Thomas

    # Reeves Stats (https://fmmvibe.com/forums/topic/46412-hexers-workshop-its-all-about-hex-fmm21-and-beyond/?do=findComment&comment=493416)
    # BYTES POS: 6835997
    # 8B5D0000 AC050500 E2F8CE1E 150809E5 F60A0B09 0A0B0707 08070709 0508ED0C EC0C09C4 CE0CB0B0 BAB00101 01010101 0101010C 0C0C1401 0114094B 004B004E 114811E9 0A0008C8 1E00B000 46
    # SID      ???????? ???????? ???????? ???????? ???????? ???????? ???????? ???????? ???????? ????GK?? LBCBRBDM LMCMRMLM AMRWCFWB WB?????? ???????? ???????? ???????? ???????? ??

    # 00000052 0000300D 00000004 02710C00 00FFFFFF FFFF0000 14060500 8B5D0000 06000002 011E0000 000B0F72 00000820 01010AF7 0100 - Reeves
    # 0100004e 0000720f 00000208 023b0f00 00ffffff ff470000 0a090802 8b5d0000 0a000005 021e0000 000b0f72 0000781e 0000ff4d 0a00 - Reeves
    # 01000050 0000300D 00000006 02730C00 00FFFFFF FFFF0300 12151003 8B5D0000 08000001 011E0000 000B0F72 0000401F 00000AFB 0100
    # 0000004F 00002A0D 00000002 01710C00 00FFFFFF FFFF0000 14050501 8B5D0000 06000002 011E0000 000B0F72 0000DC1E 00000AFF 0100
    # 00000051 01002A0D 01000001 00710C00 02FFFFFF FFFF0000 14121001 8B5D0000 07000001 001E0000 000B0F72 0000A41F 00000A02 0200

    # 00000064 00009F0C 00000000 00B40C00 00FFFFFF FFFF0000 14000000 5E5D0000 06000000 00100000 000FDE71 00001027 00000105 0000 - Leeson
    # 00000055 01009B0C 00000001 01B00C00 05FFFFFF FFFF0200 14140B00 5E5D0000 06000000 00100000 0002DE71 00003421 02020107 0000 - Leeson
    # 00000064 00008A0C 00000000 009F0C00 00FFFFFF FFFF0000 14000000 5E5D0000 06000000 00100000 000FDE71 00001027 0000FF07 0000
    # 00000052 0000820C 00000003 02970C00 03FFFFFF FFFF0300 14140E00 5E5D0000 06000000 00100000 0002DE71 00000820 01010171 0000

    # 0000005A 0200280C 00000000 00470900 01FFFF3F FFFF0000 0E080700 DB560000 06000000 000C0000 0013216A 00002823 010105AD 0800 - Franklin
    # 0000004F 0000290C 00000001 00470900 01FFFFFF FF520000 0C171103 DB560000 07000001 010C0000 0007216A 0000DC1E 0101FFAD 0800
    # 0000005E 0000190C 00000000 00470900 00FFFFFF FFFF0000 0E000000 DB560000 06000000 000C0000 0011216A 0000B824 0000FFAD 0800
    # 00000049 00003D0C 02040002 015E0900 00FFFFFF FFFF0100 08120E01 DB560000 06000000 000C0000 0007216A 0000841C 02020629 0901
    # 00000058 00002D0C 00000000 005E0900 00FFFFFF FFFF0000 0E000000 DB560000 06000000 000C0000 000F216A 00006022 0000FF29 0900
    # 00000054 01004F0C 00040000 00750900 01FFFFFF FF3C0000 0A181301 DB560000 06000000 000C0000 0007216A 0000D020 0000FF99 0901

    # 0000004C 05026C0F 00000101 00EE0C00 02FFFFFF FFFF0100 090C0500 4F300000 09000002 01060000 0009FF3E 0000B01D 0202087B 0A00 - Stratulis
    # 0000005B 0000CC0F 00000000 00400D00 00FFFFFF FFFF0000 0A000000 4F300000 06000000 00060000 0012FF3E 00008C23 0000FF9A 0A00
    # 00000053 0100C70F 02000002 003F0D00 01FFFFFF FFFF0100 0B050100 4F300000 06000001 01060000 0009FF3E 00006C20 00000899 0A00
    # 01000053 0700C70F 04000008 00400D00 00FFFFFF FFFF0100 080A0800 4F300000 08000003 01060000 0009FF3E 00006C20 00000899 0A00
